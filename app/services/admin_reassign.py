"""Manual booking reassign (A-REASSIGN) — DISPATCH_FLOW.md §Manual reassign."""
from __future__ import annotations

import datetime as dt
import uuid

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_BLOCKED_STATUSES = frozenset(
    {
        "in_progress",
        "completed",
        "cancelled",
        "disputed",
        "failed_no_pujari",
        "abandoned",
    }
)


async def manual_reassign(
    db: AsyncSession,
    *,
    booking_id: uuid.UUID,
    new_pujari_id: uuid.UUID,
    admin_user_id: uuid.UUID,
) -> dict:
    """Clear-revoke-insert in one transaction; trigger 3 confirms the new pujari."""
    row = (
        await db.execute(
            text(
                """
                SELECT
                    b.status_id,
                    st.code AS status,
                    b.pujari_id,
                    b.intended_pujari_id
                FROM bookings b
                JOIN status_types st ON st.id = b.status_id
                WHERE b.id = :bid
                FOR UPDATE
                """
            ),
            {"bid": str(booking_id)},
        )
    ).mappings().first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found.")
    if row["status"] in _BLOCKED_STATUSES:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Cannot reassign a booking in this state — use dispute resolution instead.",
        )
    old_pujari_id = row["pujari_id"]
    if old_pujari_id is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Booking has no assigned pujari to reassign from.",
        )
    if old_pujari_id == new_pujari_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "New pujari must differ from the current assignment.",
        )

    pujari_exists = (
        await db.execute(
            text("SELECT 1 FROM pujaris WHERE id = :pid"),
            {"pid": str(new_pujari_id)},
        )
    ).scalar_one_or_none()
    if pujari_exists is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Target pujari not found.")

    status_rows = (
        await db.execute(
            text(
                """
                SELECT code, id FROM status_types
                WHERE (domain = 'assignment' AND code IN ('accepted', 'revoked'))
                   OR (domain = 'booking' AND code = 'confirmed')
                """
            )
        )
    ).all()
    status_ids = {row[0]: row[1] for row in status_rows}
    accepted_id = status_ids.get("accepted")
    revoked_id = status_ids.get("revoked")
    if accepted_id is None or revoked_id is None:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Deployment configuration error. Operations alerted.",
        )

    # Step 1 — clear booking pujari fields + admin audit history row.
    await db.execute(
        text(
            """
            UPDATE bookings
            SET pujari_id = NULL, intended_pujari_id = NULL, updated_at = now()
            WHERE id = :bid
            """
        ),
        {"bid": str(booking_id)},
    )
    await db.execute(
        text(
            """
            INSERT INTO booking_status_history (id, booking_id, status_id, changed_by, changed_at)
            VALUES (gen_random_uuid(), :bid, :sid, :uid, now())
            """
        ),
        {"bid": str(booking_id), "sid": row["status_id"], "uid": str(admin_user_id)},
    )

    # Step 2 — revoke the old accepted assignment (never 'rejected').
    await db.execute(
        text(
            """
            UPDATE booking_assignments
            SET status_id = :revoked_id
            WHERE booking_id = :bid
              AND pujari_id = :old_pid
              AND status_id = :accepted_id
            """
        ),
        {
            "revoked_id": revoked_id,
            "bid": str(booking_id),
            "old_pid": str(old_pujari_id),
            "accepted_id": accepted_id,
        },
    )

    # Step 3 — insert accepted assignment; trigger 3 sets pujari + confirmed history.
    new_assignment_id = uuid.uuid4()
    await db.execute(
        text(
            """
            INSERT INTO booking_assignments (
                id, booking_id, pujari_id, status_id, offered_at, expires_at, responded_at
            ) VALUES (
                :aid, :bid, :new_pid, :accepted_id, now(), now() + interval '5 minutes', now()
            )
            """
        ),
        {
            "aid": str(new_assignment_id),
            "bid": str(booking_id),
            "new_pid": str(new_pujari_id),
            "accepted_id": accepted_id,
        },
    )

    after = (
        await db.execute(
            text(
                """
                SELECT b.pujari_id, st.code AS status
                FROM bookings b
                JOIN status_types st ON st.id = b.status_id
                WHERE b.id = :bid
                """
            ),
            {"bid": str(booking_id)},
        )
    ).mappings().first()
    if after is None or after["pujari_id"] != new_pujari_id:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Reassign did not complete — booking state inconsistent.",
        )

    return {
        "booking_id": booking_id,
        "old_pujari_id": old_pujari_id,
        "new_pujari_id": new_pujari_id,
        "assignment_id": new_assignment_id,
        "status": after["status"],
        "reassigned_at": dt.datetime.now(dt.UTC),
    }
