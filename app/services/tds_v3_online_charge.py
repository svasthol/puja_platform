"""TDS v3 online charge lifecycle — prevent async double-charge vs offline collection."""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import Payment, Refund
from app.services.tds_v3_fy_writer import load_booking_tds_v3_snapshot, update_tds_collected_online

log = structlog.get_logger()

_PAISA = Decimal("0.01")


async def _load_booking_charge_row(
    db: AsyncSession, *, booking_id: uuid.UUID, for_update: bool = False
) -> dict[str, Any] | None:
    lock = "FOR UPDATE" if for_update else ""
    return (
        await db.execute(
            text(
                f"""
                SELECT total_amount,
                       tds_liability_inr,
                       tds_collected_online,
                       tds_razorpay_order_id,
                       tds_online_charge_closed_at,
                       amount_due_offline,
                       balance_collected_at
                FROM bookings
                WHERE id = :bid
                {lock}
                """
            ),
            {"bid": str(booking_id)},
        )
    ).mappings().first()


async def close_tds_razorpay_order(
    db: AsyncSession, *, booking_id: uuid.UUID, reason: str
) -> None:
    """Expire async checkout — webhook must not shrink offline after this (refund if paid late)."""
    await db.execute(
        text(
            """
            UPDATE bookings
            SET tds_razorpay_order_id = NULL,
                tds_online_charge_closed_at = COALESCE(tds_online_charge_closed_at, now()),
                updated_at = now()
            WHERE id = :bid
            """
        ),
        {"bid": str(booking_id)},
    )
    log.info("tds_razorpay_order_closed", booking_id=str(booking_id), reason=reason)


async def ensure_recovery_pending(
    db: AsyncSession,
    *,
    booking_id: uuid.UUID,
    pujari_id: uuid.UUID,
    fy_start: dt.date,
    tds_amount: Decimal,
) -> None:
    await db.execute(
        text(
            """
            INSERT INTO pujari_tds_recovery (
                id, pujari_id, booking_id, fy_start, tds_amount, status
            ) VALUES (
                gen_random_uuid(), :pid, :bid, :fy, :amt, 'pending'
            )
            ON CONFLICT (booking_id) DO NOTHING
            """
        ),
        {
            "pid": str(pujari_id),
            "bid": str(booking_id),
            "fy": fy_start,
            "amt": str(tds_amount.quantize(_PAISA)),
        },
    )


async def finalize_unresolved_tds_before_offline_collection(
    db: AsyncSession,
    *,
    booking_id: uuid.UUID,
    pujari_id: uuid.UUID,
) -> None:
    """Resolve pending async TDS before pujari records offline cash (offline stays full → recovery)."""
    row = await _load_booking_charge_row(db, booking_id=booking_id, for_update=True)
    if row is None:
        return
    liability = Decimal(str(row["tds_liability_inr"] or 0)).quantize(_PAISA)
    collected = Decimal(str(row["tds_collected_online"] or 0)).quantize(_PAISA)
    if liability <= 0 or collected >= liability:
        return
    if row["balance_collected_at"] is not None:
        return

    from app.services.tds_accrual_service import fy_start_for_date

    fy_start = fy_start_for_date(dt.date.today())
    await close_tds_razorpay_order(db, booking_id=booking_id, reason="before_offline_collection")
    await ensure_recovery_pending(
        db,
        booking_id=booking_id,
        pujari_id=pujari_id,
        fy_start=fy_start,
        tds_amount=liability,
    )
    turnover = Decimal(str(row["total_amount"])).quantize(_PAISA)
    await db.execute(
        text(
            """
            UPDATE bookings
            SET tds_collected_online = 0,
                amount_due_offline = :offline,
                updated_at = now()
            WHERE id = :bid
            """
        ),
        {"bid": str(booking_id), "offline": str(turnover)},
    )


async def _record_tds_payment(
    db: AsyncSession,
    *,
    booking_id: uuid.UUID,
    amount_inr: Decimal,
    gateway_txn_id: str,
) -> uuid.UUID:
    """Idempotent TDS payment row (separate from booking-fee payment)."""
    idem = f"tds:{gateway_txn_id}"
    existing = (
        await db.execute(
            text("SELECT id FROM payments WHERE idempotency_key = :k"),
            {"k": idem},
        )
    ).scalar_one_or_none()
    if existing is not None:
        return uuid.UUID(str(existing))
    pid = uuid.uuid4()
    db.add(
        Payment(
            id=pid,
            booking_id=booking_id,
            amount=float(amount_inr.quantize(_PAISA)),
            idempotency_key=idem,
            gateway_txn_id=gateway_txn_id,
            status="success",
            created_at=dt.datetime.now(dt.UTC),
        )
    )
    return pid


async def _enqueue_tds_late_refund(
    db: AsyncSession,
    *,
    booking_id: uuid.UUID,
    payment_id: uuid.UUID,
    amount_inr: Decimal,
    reason: str,
) -> None:
    amt = amount_inr.quantize(_PAISA)
    existing = (
        await db.execute(
            text(
                """
                SELECT id, amount FROM refunds
                WHERE payment_id = :pid AND status = 'pending'
                LIMIT 1
                """
            ),
            {"pid": str(payment_id)},
        )
    ).mappings().first()
    if existing is not None:
        merged = (Decimal(str(existing["amount"])) + amt).quantize(_PAISA)
        await db.execute(
            text(
                """
                UPDATE refunds
                SET amount = :amt, reason = :reason, updated_at = now()
                WHERE id = :rid
                """
            ),
            {"rid": str(existing["id"]), "amt": str(merged), "reason": reason},
        )
        return
    refund_id = uuid.uuid4()
    db.add(
        Refund(
            id=refund_id,
            payment_id=payment_id,
            booking_id=booking_id,
            amount=float(amount_inr.quantize(_PAISA)),
            reason=reason,
            status="pending",
            attempt_count=0,
            next_attempt_at=dt.datetime.now(dt.UTC),
            created_at=dt.datetime.now(dt.UTC),
        )
    )


async def handle_tds_payment_webhook(
    db: AsyncSession,
    *,
    booking_id: uuid.UUID,
    order_id: str | None,
    amount_inr: Decimal,
    gateway_txn_id: str,
) -> dict[str, str]:
    """Idempotent TDS capture — never shrink offline after offline collection or closed order."""
    await db.execute(
        text("SELECT id FROM bookings WHERE id = :bid FOR UPDATE"),
        {"bid": str(booking_id)},
    )
    row = await _load_booking_charge_row(db, booking_id=booking_id, for_update=False)
    if row is None:
        return {"status": "booking_missing"}

    liability = Decimal(str(row["tds_liability_inr"] or 0)).quantize(_PAISA)
    collected = Decimal(str(row["tds_collected_online"] or 0)).quantize(_PAISA)
    turnover = Decimal(str(row["total_amount"])).quantize(_PAISA)
    if liability <= 0:
        payment_id = await _record_tds_payment(
            db, booking_id=booking_id, amount_inr=amount_inr, gateway_txn_id=gateway_txn_id
        )
        await _enqueue_tds_late_refund(
            db,
            booking_id=booking_id,
            payment_id=payment_id,
            amount_inr=amount_inr,
            reason="tds_unexpected_capture",
        )
        return {"status": "unexpected_tds_refund"}

    if collected >= liability:
        await _record_tds_payment(
            db, booking_id=booking_id, amount_inr=amount_inr, gateway_txn_id=gateway_txn_id
        )
        return {"status": "idempotent"}

    payment_id = await _record_tds_payment(
        db, booking_id=booking_id, amount_inr=amount_inr, gateway_txn_id=gateway_txn_id
    )

    stored_order = row["tds_razorpay_order_id"]
    order_open = stored_order and order_id and str(stored_order) == str(order_id)
    charge_closed = row["tds_online_charge_closed_at"] is not None
    offline_already_full = Decimal(str(row["amount_due_offline"] or 0)).quantize(
        _PAISA
    ) >= turnover and collected == 0
    recovery_pending = (
        await db.execute(
            text(
                """
                SELECT 1 FROM pujari_tds_recovery
                WHERE booking_id = :bid AND status = 'pending'
                """
            ),
            {"bid": str(booking_id)},
        )
    ).scalar_one_or_none()

    must_refund = (
        row["balance_collected_at"] is not None
        or charge_closed
        or recovery_pending
        or offline_already_full
        or not order_open
    )

    if must_refund:
        await _enqueue_tds_late_refund(
            db,
            booking_id=booking_id,
            payment_id=payment_id,
            amount_inr=amount_inr,
            reason="tds_late_or_double_capture",
        )
        log.warning(
            "tds_webhook_late_refund",
            booking_id=str(booking_id),
            order_id=order_id,
            charge_closed=charge_closed,
            recovery=recovery_pending is not None,
        )
        return {"status": "late_capture_refund_queued"}

    await update_tds_collected_online(
        db, booking_id=booking_id, tds_collected_online_inr=amount_inr
    )
    await db.execute(
        text(
            """
            UPDATE pujari_tds_recovery
            SET status = 'void', recovered_at = now()
            WHERE booking_id = :bid AND status = 'pending'
            """
        ),
        {"bid": str(booking_id)},
    )
    await close_tds_razorpay_order(db, booking_id=booking_id, reason="collected")
    return {"status": "tds_collected"}
