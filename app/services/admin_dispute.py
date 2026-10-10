"""Admin dispute resolution (A-DISPUTE)."""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import tds_accrual_service


async def open_dispute(
    db: AsyncSession,
    *,
    booking_id: uuid.UUID,
    admin_user_id: uuid.UUID,
    dispute_type: str,
) -> dict:
    """Transition in_progress -> disputed with guarded UPDATE."""
    row = (
        await db.execute(
            text(
                """
                SELECT
                    b.status_id,
                    st.code AS status,
                    b.payment_mode,
                    b.amount_due_offline,
                    b.balance_collected_at
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
    if row["status"] != "in_progress":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Dispute resolution applies only to in_progress bookings.",
        )

    disputed_id = (
        await db.execute(
            text(
                "SELECT id FROM status_types WHERE domain = 'booking' AND code = 'disputed'"
            )
        )
    ).scalar_one_or_none()
    if disputed_id is None:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Deployment configuration error. Operations alerted.",
        )

    in_progress_id = row["status_id"]
    result = await db.execute(
        text(
            """
            UPDATE bookings
            SET status_id = :disputed_id, updated_at = now()
            WHERE id = :bid AND status_id = :expected
            """
        ),
        {
            "disputed_id": disputed_id,
            "bid": str(booking_id),
            "expected": in_progress_id,
        },
    )
    if result.rowcount == 0:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Booking state changed — refresh and retry.",
        )

    await db.execute(
        text(
            """
            INSERT INTO booking_status_history (id, booking_id, status_id, changed_by, changed_at)
            VALUES (gen_random_uuid(), :bid, :sid, :uid, now())
            """
        ),
        {"bid": str(booking_id), "sid": disputed_id, "uid": str(admin_user_id)},
    )

    offline_note: str | None = None
    tds_reversal: dict | None = None
    offline_due = Decimal(str(row["amount_due_offline"] or 0))
    if dispute_type == "offline_non_payment" or (
        row["payment_mode"] == "advance_balance" and offline_due > 0
    ):
        if row["balance_collected_at"] is None and offline_due > 0:
            offline_note = (
                f"Offline balance (₹{offline_due}) is between customer and pujari — "
                "not refundable via the platform. Resolve offline collection directly."
            )
        elif offline_due > 0:
            offline_note = (
                f"Pujari recorded offline collection (₹{offline_due}). "
                "Platform refunds apply to the online portion only."
            )

    if dispute_type == "offline_non_payment" and row["balance_collected_at"] is not None:
        tds_reversal = await tds_accrual_service.reverse_tds_if_accrued(
            db, booking_id=booking_id
        )

    return {
        "booking_id": booking_id,
        "previous_status": row["status"],
        "status": "disputed",
        "dispute_type": dispute_type,
        "disputed_at": dt.datetime.now(dt.UTC),
        "offline_balance_note": offline_note,
        "tds_reversal": tds_reversal,
    }
