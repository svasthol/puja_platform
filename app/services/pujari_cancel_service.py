"""
Pujari cancel assigned booking (B-CANCEL) — DISPATCH_FLOW §Pujari cancel.

Assigned pujari drops out of a `confirmed` booking (not yet `in_progress`).
Default policy: return to `requested`, clear assignment, revoke accepted row,
enqueue `rebroadcast_booking(fresh=True)`. No customer refund — ops re-dispatch.
"""
from __future__ import annotations

import uuid

import structlog
from fastapi import HTTPException, status as http
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import StaleBookingState
from app.services import booking_events
from app.services.status import status_id

log = structlog.get_logger()


async def pujari_cancel_booking(
    db: AsyncSession, *, user_id: uuid.UUID, booking_id: uuid.UUID
) -> dict:
    row = (
        await db.execute(
            text(
                """
                SELECT
                    b.id,
                    b.pujari_id,
                    b.status_id,
                    st.code AS status
                FROM bookings b
                JOIN status_types st ON st.id = b.status_id
                JOIN pujaris pj ON pj.id = b.pujari_id
                WHERE b.id = :bid
                  AND pj.user_id = :uid
                  AND b.cancelled_at IS NULL
                FOR UPDATE OF b
                """
            ),
            {"bid": str(booking_id), "uid": str(user_id)},
        )
    ).mappings().first()
    if row is None:
        raise HTTPException(
            http.HTTP_403_FORBIDDEN,
            "Not the assigned pujari for this booking.",
        )
    if row["status"] != "confirmed":
        raise HTTPException(
            http.HTTP_409_CONFLICT,
            "Booking must be confirmed to cancel assignment.",
        )

    pujari_id = row["pujari_id"]
    confirmed_id = row["status_id"]
    requested_id = await status_id(db, "booking", "requested")
    revoked_id = await status_id(db, "assignment", "revoked")
    accepted_id = await status_id(db, "assignment", "accepted")

    result = await db.execute(
        text(
            """
            UPDATE bookings
            SET pujari_id = NULL,
                intended_pujari_id = NULL,
                status_id = :requested_id,
                updated_at = now()
            WHERE id = :bid
              AND status_id = :confirmed_id
              AND pujari_id = :pid
              AND cancelled_at IS NULL
            """
        ),
        {
            "requested_id": requested_id,
            "bid": str(booking_id),
            "confirmed_id": confirmed_id,
            "pid": str(pujari_id),
        },
    )
    if result.rowcount == 0:
        raise StaleBookingState()

    await db.execute(
        text(
            """
            INSERT INTO booking_status_history (id, booking_id, status_id, changed_by, changed_at)
            VALUES (gen_random_uuid(), :bid, :sid, :uid, now())
            """
        ),
        {"bid": str(booking_id), "sid": requested_id, "uid": str(user_id)},
    )

    await db.execute(
        text(
            """
            UPDATE booking_assignments
            SET status_id = :revoked_id
            WHERE booking_id = :bid
              AND pujari_id = :pid
              AND status_id = :accepted_id
            """
        ),
        {
            "revoked_id": revoked_id,
            "bid": str(booking_id),
            "pid": str(pujari_id),
            "accepted_id": accepted_id,
        },
    )

    log.info(
        "pujari_cancel",
        booking_id=str(booking_id),
        pujari_id=str(pujari_id),
        reliability_signal=True,
    )
    await booking_events.publish_booking_event(
        str(booking_id), "status_changed", status="requested"
    )
    return {
        "booking_id": str(booking_id),
        "status": "requested",
        "enqueue_rebroadcast": str(booking_id),
    }
