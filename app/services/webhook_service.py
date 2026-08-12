"""
Razorpay webhook handler (spec DISPATCH_FLOW step 4, API_CONTRACTS webhooks).

ONE transaction:
  a. INSERT payments (idempotency_key dedupes retries).
  b. SELECT booking FOR UPDATE.
  c. payment_pending -> set paid_at, status 'requested', history row,
     convert hold (released_at = converted_at = now), enqueue broadcast.
     Does NOT write booking_dispatch_state — the worker owns that row (§21.6.C).
  d. abandoned / late / double-paid -> record payment + INSERT refunds row
     (reason='late_payment'), notify, and STILL return 200 to Razorpay.

Always returns 200 once the payment is recorded. The ex_bookings_intended_no_overlap
exclusion is caught here (not the generic handler) so the auto-refund path runs.
"""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import structlog
from psycopg.errors import ExclusionViolation
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, SlotHold
from app.models.payment import Payment, Refund
from app.services import booking_events
from app.services.status import status_id

log = structlog.get_logger()


async def _insert_late_refund(db: AsyncSession, *, payment: Payment, booking: Booking) -> None:
    """Full auto-refund of the online amount for late/double-paid cases."""
    db.add(
        Refund(
            id=uuid.uuid4(),
            payment_id=payment.id,
            booking_id=booking.id,
            amount=Decimal(str(booking.amount_due_online)),
            reason="late_payment",
            status="pending",
            attempt_count=0,
            next_attempt_at=dt.datetime.now(dt.UTC),
            created_at=dt.datetime.now(dt.UTC),
        )
    )


async def handle_payment_captured(
    db: AsyncSession,
    *,
    booking_id: uuid.UUID,
    gateway_txn_id: str,
    idempotency_key: str,
    amount_paise: int,
) -> dict:
    now = dt.datetime.now(dt.UTC)

    # (a) record payment — idempotency_key UNIQUE dedupes retries
    payment = Payment(
        id=uuid.uuid4(),
        booking_id=booking_id,
        amount=Decimal(amount_paise) / Decimal(100),
        idempotency_key=idempotency_key,
        gateway_txn_id=gateway_txn_id,
        status="success",
        created_at=now,
    )
    db.add(payment)
    try:
        await db.flush()
    except IntegrityError as exc:
        diag = getattr(getattr(exc, "orig", None), "diag", None)
        cname = getattr(diag, "constraint_name", "") if diag else ""
        if cname in ("payments_idempotency_key_key", "ux_payments_one_success_per_booking"):
            log.info("webhook_duplicate_ack", constraint=cname, booking_id=str(booking_id))
            return {"status": "already_processed"}
        raise

    # (b) lock booking
    booking = (
        await db.execute(select(Booking).where(Booking.id == booking_id).with_for_update())
    ).scalar_one_or_none()
    if booking is None:
        log.error("webhook_booking_missing", booking_id=str(booking_id))
        return {"status": "booking_missing"}

    pending_id = await status_id(db, "booking", "payment_pending")
    requested_id = await status_id(db, "booking", "requested")

    # (d) sweep already abandoned it, or it's terminal -> auto-refund, no resurrect
    if booking.status_id != pending_id or booking.cancelled_at is not None:
        await _insert_late_refund(db, payment=payment, booking=booking)
        log.info("webhook_late_autorefund", booking_id=str(booking_id))
        return {"status": "auto_refund_initiated"}

    # (c) happy path — arm paid_at, flip to requested. The intended-overlap
    # exclusion may fire here if another customer paid this window first.
    # Wrap ONLY the flip in a SAVEPOINT so a violation rolls back the flip but
    # keeps the payment row (which we must retain), then we auto-refund.
    try:
        async with db.begin_nested():  # SAVEPOINT
            booking.paid_at = now
            booking.status_id = requested_id
            booking.updated_at = now
            await db.flush()
    except IntegrityError as exc:
        if isinstance(getattr(exc, "orig", None), ExclusionViolation):
            await _insert_late_refund(db, payment=payment, booking=booking)
            log.info("webhook_overlap_autorefund", booking_id=str(booking_id))
            return {"status": "auto_refund_initiated"}
        raise

    # history + convert hold
    await db.execute(
        text(
            "INSERT INTO booking_status_history (id, booking_id, status_id, changed_by, changed_at) "
            "VALUES (gen_random_uuid(), :bid, :sid, NULL, now())"
        ),
        {"bid": str(booking_id), "sid": requested_id},
    )
    if booking.hold_id:
        hold = (
            await db.execute(select(SlotHold).where(SlotHold.id == booking.hold_id))
        ).scalar_one_or_none()
        if hold and hold.released_at is None:
            hold.released_at = now
            hold.converted_at = now

    log.info("webhook_payment_confirmed", booking_id=str(booking_id), dispatch_mode=booking.dispatch_mode)
    await booking_events.publish_booking_event(
        str(booking_id), "status_changed", status="requested", dispatch_mode=booking.dispatch_mode
    )
    if booking.dispatch_mode == "direct":
        log.warning(
            "webhook_direct_mode_coerced_to_broadcast",
            booking_id=str(booking_id),
        )
    return {"status": "confirmed", "enqueue_broadcast": str(booking_id)}
