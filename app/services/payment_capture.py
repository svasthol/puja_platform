"""
Shared Razorpay capture handler (webhook REL-004, client verify REL-015, reconcile REL-005).

ONE transaction:
  a. SELECT booking FOR UPDATE.
  b. Check-then-insert payments (pay_… keys; duplicate_capture when booking already paid).
  c. payment_pending -> set paid_at, status 'requested', history row,
     convert hold (released_at = converted_at = now), enqueue broadcast after commit.
     Does NOT write booking_dispatch_state — the worker owns that row (§21.6.C).
  d. abandoned / late / double-paid -> record payment + INSERT refunds row.
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
from app.services.pricing import platform_charge_amount
from app.services.status import status_id

log = structlog.get_logger()


def _refund_cap(booking: Booking) -> Decimal:
    return platform_charge_amount(
        payment_mode=booking.payment_mode,
        booking_fee=Decimal(str(booking.booking_fee or 0)),
        amount_due_online=Decimal(str(booking.amount_due_online)),
    )


async def _insert_refund(
    db: AsyncSession,
    *,
    payment: Payment,
    booking: Booking,
    amount: Decimal | None = None,
    reason: str = "late_payment",
) -> None:
    """Auto-refund for late/double-paid/mismatched captures."""
    refund_amt = amount if amount is not None else _refund_cap(booking)
    if refund_amt <= 0:
        return
    db.add(
        Refund(
            id=uuid.uuid4(),
            payment_id=payment.id,
            booking_id=booking.id,
            amount=refund_amt,
            reason=reason,
            status="pending",
            attempt_count=0,
            next_attempt_at=dt.datetime.now(dt.UTC),
            created_at=dt.datetime.now(dt.UTC),
        )
    )


async def _insert_payment_split(
    db: AsyncSession, *, payment_id: uuid.UUID, booking: Booking
) -> None:
    """Platform revenue split — trigger 1 computes net_pujari_amount."""
    if booking.payment_mode != "booking_fee":
        return
    fee = Decimal(str(booking.booking_fee or 0))
    if fee <= 0:
        return
    await db.execute(
        text(
            """
            INSERT INTO payment_splits (id, payment_id, platform_fee, gst_amount)
            VALUES (gen_random_uuid(), :pid, :fee, 0)
            ON CONFLICT (payment_id) DO NOTHING
            """
        ),
        {"pid": str(payment_id), "fee": str(fee)},
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
    pay_key = idempotency_key or gateway_txn_id

    booking_row = (
        await db.execute(select(Booking).where(Booking.id == booking_id).with_for_update())
    ).scalar_one_or_none()
    if booking_row is None:
        log.error("payment_capture_booking_missing", booking_id=str(booking_id))
        return {"status": "booking_missing"}

    existing = (
        await db.execute(
            text(
                """
                SELECT id FROM payments
                WHERE gateway_txn_id = :k OR idempotency_key = :k
                LIMIT 1
                """
            ),
            {"k": pay_key},
        )
    ).scalar_one_or_none()
    if existing is not None:
        log.info("payment_capture_duplicate_ack", booking_id=str(booking_id), pay_key=pay_key)
        return {"status": "already_processed"}

    pending_id = await status_id(db, "booking", "payment_pending")
    requested_id = await status_id(db, "booking", "requested")

    has_success_payment = (
        await db.execute(
            text(
                "SELECT 1 FROM payments WHERE booking_id = :bid AND status = 'success' LIMIT 1"
            ),
            {"bid": str(booking_id)},
        )
    ).scalar_one_or_none() is not None
    booking_already_paid = (
        booking_row.paid_at is not None or booking_row.status_id != pending_id
    )

    expected_paise = int((_refund_cap(booking_row) * 100).quantize(Decimal("1")))
    captured = Decimal(amount_paise) / Decimal(100)
    amount_mismatch = expected_paise > 0 and amount_paise != expected_paise

    payment_status = (
        "duplicate_capture"
        if booking_already_paid and has_success_payment
        else "success"
    )

    orphan_success_id = None
    if (
        not booking_already_paid
        and has_success_payment
        and payment_status == "success"
    ):
        orphan_success_id = (
            await db.execute(
                text(
                    """
                    SELECT id FROM payments
                    WHERE booking_id = :bid AND status = 'success'
                    LIMIT 1
                    """
                ),
                {"bid": str(booking_id)},
            )
        ).scalar_one_or_none()

    payment: Payment | None = None
    if orphan_success_id is not None:
        payment = (
            await db.execute(select(Payment).where(Payment.id == orphan_success_id))
        ).scalar_one()
        payment.amount = captured
        payment.gateway_txn_id = gateway_txn_id or pay_key
        payment.idempotency_key = pay_key
        await db.flush()
        log.info(
            "payment_capture_orphan_success_retry",
            booking_id=str(booking_id),
            payment_id=str(orphan_success_id),
            new_pay_key=pay_key,
        )
    elif payment_status == "duplicate_capture":
        payment = Payment(
            id=uuid.uuid4(),
            booking_id=booking_id,
            amount=captured,
            idempotency_key=pay_key,
            gateway_txn_id=gateway_txn_id or pay_key,
            status=payment_status,
            created_at=now,
        )
        db.add(payment)
        await db.flush()
    else:
        payment = Payment(
            id=uuid.uuid4(),
            booking_id=booking_id,
            amount=captured,
            idempotency_key=pay_key,
            gateway_txn_id=gateway_txn_id or pay_key,
            status=payment_status,
            created_at=now,
        )
        db.add(payment)
        try:
            await db.flush()
        except IntegrityError as exc:
            diag = getattr(getattr(exc, "orig", None), "diag", None)
            cname = getattr(diag, "constraint_name", "") if diag else ""
            log.info(
                "payment_capture_duplicate_ack_fallback",
                constraint=cname,
                booking_id=str(booking_id),
            )
            return {"status": "already_processed"}

    booking = booking_row
    assert payment is not None

    if payment_status == "duplicate_capture":
        await _insert_refund(
            db,
            payment=payment,
            booking=booking,
            amount=captured,
            reason="duplicate_payment",
        )
        log.info(
            "payment_capture_duplicate_refund",
            booking_id=str(booking_id),
            pay_key=pay_key,
        )
        return {"status": "auto_refund_initiated", "reason": "duplicate_capture"}

    if amount_mismatch:
        await _insert_refund(db, payment=payment, booking=booking, amount=captured)
        log.warning(
            "payment_capture_amount_mismatch_autorefund",
            booking_id=str(booking_id),
            expected_paise=expected_paise,
            got_paise=amount_paise,
        )
        return {"status": "auto_refund_initiated", "reason": "amount_mismatch"}

    if booking.status_id != pending_id or booking.cancelled_at is not None:
        await _insert_refund(db, payment=payment, booking=booking)
        log.info("payment_capture_late_autorefund", booking_id=str(booking_id))
        return {"status": "auto_refund_initiated"}

    try:
        async with db.begin_nested():
            booking.paid_at = now
            booking.status_id = requested_id
            booking.updated_at = now
            booking.reconcile_next_at = None
            await db.flush()
            await _insert_payment_split(db, payment_id=payment.id, booking=booking)
    except IntegrityError as exc:
        if isinstance(getattr(exc, "orig", None), ExclusionViolation):
            await _insert_refund(db, payment=payment, booking=booking)
            log.info("payment_capture_overlap_autorefund", booking_id=str(booking_id))
            return {"status": "auto_refund_initiated"}
        raise

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

    log.info(
        "payment_capture_confirmed",
        booking_id=str(booking_id),
        dispatch_mode=booking.dispatch_mode,
    )
    await booking_events.publish_booking_event(
        str(booking_id), "status_changed", status="requested", dispatch_mode=booking.dispatch_mode
    )
    if booking.dispatch_mode == "direct":
        log.warning(
            "payment_capture_direct_coerced_to_broadcast",
            booking_id=str(booking_id),
        )
    return {"status": "confirmed", "enqueue_broadcast": str(booking_id)}