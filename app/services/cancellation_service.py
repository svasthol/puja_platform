"""
Cancellation (spec DISPATCH_FLOW "Cancellation", API_CONTRACTS cancel).

State-gated in the app AND by bu_bookings_cancel_guard trigger. One transaction:
set cancelled_at + flip status to 'cancelled' + history row + refunds row.
Refund is capped at platform-collected money (booking_fee at launch; legacy modes
use amount_due_online). Offline puja balance is never refunded via Razorpay.

Refund reason/percent by status:
  payment_pending -> void, NO refund row (nothing captured).
  requested       -> 100% of platform charge (booking_fee or amount_due_online).
  confirmed       -> booking_fee: 0%; legacy: policy % of amount_due_online.
  terminal/in_progress/completed -> blocked (409/410); admin override only.
"""
from __future__ import annotations

import datetime as dt
import uuid
import zoneinfo
from decimal import Decimal

import structlog
from fastapi import HTTPException, status as http
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import StaleBookingState
from app.models.booking import Booking
from app.models.lookups import CancellationPolicy
from app.models.payment import Payment, Refund
from app.schemas.booking import CancelResponse
from app.services.pricing import customer_cancel_refund_amount
from app.services.status import status_id

log = structlog.get_logger()
settings = get_settings()
_TZ = zoneinfo.ZoneInfo(settings.PLATFORM_TIMEZONE)

_CANCELLABLE = {"payment_pending", "requested", "confirmed"}


async def cancel_booking(
    db: AsyncSession, *, user_id: uuid.UUID, booking_id: uuid.UUID
) -> CancelResponse:
    now = dt.datetime.now(dt.UTC)

    booking = (
        await db.execute(select(Booking).where(Booking.id == booking_id).with_for_update())
    ).scalar_one_or_none()
    if booking is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "Booking not found.")
    if booking.user_id != user_id:
        raise HTTPException(http.HTTP_403_FORBIDDEN, "Not your booking.")
    if booking.cancelled_at is not None:
        raise HTTPException(http.HTTP_410_GONE, "Booking already terminal.")

    # resolve current status code
    code = (
        await db.execute(
            text("SELECT code FROM status_types WHERE id = :sid"), {"sid": booking.status_id}
        )
    ).scalar_one()
    if code not in _CANCELLABLE:
        raise HTTPException(
            http.HTTP_409_CONFLICT,
            "This booking can no longer be cancelled — contact support.",
        )

    cancelled_id = await status_id(db, "booking", "cancelled")
    expected_status_id = booking.status_id

    booking_fee = Decimal(str(booking.booking_fee or 0))
    online = Decimal(str(booking.amount_due_online))
    policy_pct = 0
    if code == "confirmed":
        policy = (
            await db.execute(
                select(CancellationPolicy).where(
                    CancellationPolicy.id == booking.cancellation_policy_id
                )
            )
        ).scalar_one()
        scheduled = dt.datetime.combine(
            booking.scheduled_date, booking.scheduled_time, tzinfo=_TZ
        )
        hours_out = (scheduled - now.astimezone(_TZ)).total_seconds() / 3600
        policy_pct = (
            policy.refund_pct_before_24h if hours_out >= 24 else policy.refund_pct_after_24h
        )
    refund_amount = customer_cancel_refund_amount(
        booking_fee=booking_fee,
        amount_due_online=online,
        payment_mode=booking.payment_mode,
        status_code=code,
        policy_pct=policy_pct,
    )

    # guarded flip + history (trigger guard also protects in_progress/completed)
    result = await db.execute(
        text(
            "UPDATE bookings SET cancelled_at = :now, status_id = :cancelled_id, updated_at = :now "
            "WHERE id = :bid AND status_id = :expected AND cancelled_at IS NULL"
        ),
        {
            "now": now,
            "cancelled_id": cancelled_id,
            "bid": str(booking_id),
            "expected": expected_status_id,
        },
    )
    if result.rowcount == 0:
        raise StaleBookingState()
    await db.execute(
        text(
            "INSERT INTO booking_status_history (id, booking_id, status_id, changed_by, changed_at) "
            "VALUES (gen_random_uuid(), :bid, :sid, :uid, now())"
        ),
        {"bid": str(booking_id), "sid": cancelled_id, "uid": str(user_id)},
    )

    # Pending offers must not linger in partner inbox after customer cancel.
    expired_assignment_id = await status_id(db, "assignment", "expired")
    await db.execute(
        text(
            """
            UPDATE booking_assignments
            SET status_id = :expired_id, responded_at = :now
            WHERE booking_id = :bid AND responded_at IS NULL
            """
        ),
        {"expired_id": expired_assignment_id, "now": now, "bid": str(booking_id)},
    )

    # refund row only if money was captured and refund > 0
    if refund_amount > 0:
        payment = (
            await db.execute(
                select(Payment).where(
                    Payment.booking_id == booking_id, Payment.status == "success"
                )
            )
        ).scalar_one_or_none()
        if payment is not None:
            db.add(
                Refund(
                    id=uuid.uuid4(),
                    payment_id=payment.id,
                    booking_id=booking_id,
                    amount=refund_amount,
                    reason="customer_cancel",
                    status="pending",
                    attempt_count=0,
                    next_attempt_at=now,
                    created_at=now,
                )
            )

    log.info("booking_cancelled", booking_id=str(booking_id), refund=str(refund_amount))

    if booking.pujari_id is not None and get_settings().TDS_ACCRUAL_ENABLED:
        from app.services.tds_v3_reversal_service import apply_facilitation_reversal

        await apply_facilitation_reversal(
            db,
            booking_id=booking_id,
            pujari_id=booking.pujari_id,
            refund_reference=f"cancel:{booking_id}",
            refund_fraction=Decimal("1"),
        )

    return CancelResponse(
        booking_id=booking_id,
        status="cancelled",
        refund_amount=refund_amount,
        refund_eta="5–7 business days" if refund_amount > 0 else "No refund applicable",
    )


def enqueue_offer_withdrawn_notification(booking_id: uuid.UUID | str) -> None:
    """Post-commit Celery enqueue — partner FCM `offer_withdrawn` (P-FCM-CUSTOMER-CANCEL)."""
    from app.workers.celery_app import celery_app

    celery_app.send_task(
        "app.workers.notifications.notify_offer_withdrawn",
        args=[str(booking_id)],
    )
