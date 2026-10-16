"""TDS v3 — apply statutory TDS at offer accept (pujari known); separate from ₹61 booking fee."""
from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from decimal import Decimal

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.pricing import load_tds_facilitation_config
from app.services.pricing_tds_v3 import compute_facilitation_accrual
from app.services import razorpay_client
from app.services.razorpay_client import RazorpayError
from app.services.tds_accrual_service import (
    _lock_fy_row,
    _pujari_compliance,
    fy_start_for_date,
)
from app.services.tds_v3_fy_writer import (
    apply_fy_turnover_and_booking_snapshot,
    load_booking_tds_v3_snapshot,
)
from app.services.tds_v3_online_charge import (
    close_tds_razorpay_order,
    ensure_recovery_pending,
    handle_tds_payment_webhook,
)

log = structlog.get_logger()


@dataclass(frozen=True)
class TdsAcceptResult:
    applied: bool
    tds_liability_inr: Decimal
    tds_collected_online_inr: Decimal
    amount_due_offline_inr: Decimal
    recovery_pending: bool
    tds_razorpay_order_id: str | None = None
    message: str | None = None


async def attempt_tds_online_collection(
    db: AsyncSession,
    *,
    booking_id: uuid.UUID,
    tds_liability_inr: Decimal,
) -> tuple[Decimal, str | None, bool]:
    """Try Razorpay order for TDS only. Returns (collected, order_id, recovery_needed)."""
    liability = tds_liability_inr.quantize(Decimal("0.01"))
    if liability <= 0:
        return Decimal("0"), None, False

    settings = get_settings()
    if settings.TDS_ACCEPT_STUB_COLLECT:
        return liability, None, False

    if not settings.RAZORPAY_KEY_ID.startswith("rzp_"):
        log.warning("tds_charge_skipped_no_razorpay", booking_id=str(booking_id))
        return Decimal("0"), None, True

    idempotency_receipt = f"tds-{str(booking_id).replace('-', '')[:24]}"
    paise = int((liability * 100).quantize(Decimal("1")))
    try:
        order_id = await razorpay_client.create_order(
            amount_paise=paise,
            receipt=idempotency_receipt,
            notes={"booking_id": str(booking_id), "purpose": "tds_facilitation"},
        )
        await db.execute(
            text(
                """
                UPDATE bookings
                SET tds_razorpay_order_id = :oid, updated_at = now()
                WHERE id = :bid
                """
            ),
            {"bid": str(booking_id), "oid": order_id},
        )
        # Order created — customer pays async; collected stays 0 until webhook/stub.
        return Decimal("0"), order_id, False
    except RazorpayError as exc:
        log.warning("tds_razorpay_order_failed", booking_id=str(booking_id), error=str(exc))
        return Decimal("0"), None, True


async def apply_tds_at_booking_confirmation(
    db: AsyncSession,
    *,
    booking_id: uuid.UUID,
    pujari_id: uuid.UUID,
) -> TdsAcceptResult:
    """T6 — FY increment + snapshot at accept; optional online TDS order (never blocks accept)."""
    if not get_settings().TDS_ACCRUAL_ENABLED:
        return TdsAcceptResult(
            applied=False,
            tds_liability_inr=Decimal("0"),
            tds_collected_online_inr=Decimal("0"),
            amount_due_offline_inr=Decimal("0"),
            recovery_pending=False,
            message="TDS accrual disabled.",
        )

    await db.execute(
        text("SELECT id FROM bookings WHERE id = :bid FOR UPDATE"),
        {"bid": str(booking_id)},
    )
    existing = await load_booking_tds_v3_snapshot(db, booking_id=booking_id)
    if existing.fy_applied_at is not None:
        return TdsAcceptResult(
            applied=True,
            tds_liability_inr=existing.tds_liability_inr,
            tds_collected_online_inr=existing.tds_collected_online_inr,
            amount_due_offline_inr=(existing.turnover_inr - existing.tds_collected_online_inr).quantize(
                Decimal("0.01")
            ),
            recovery_pending=False,
            message="TDS snapshot already applied at accept.",
        )

    row = (
        await db.execute(
            text("SELECT total_amount FROM bookings WHERE id = :bid"),
            {"bid": str(booking_id)},
        )
    ).mappings().first()
    if row is None:
        raise ValueError("Booking not found.")
    turnover = Decimal(str(row["total_amount"])).quantize(Decimal("0.01"))

    compliance = await _pujari_compliance(db, pujari_id)
    if compliance["entity_type"] is None:
        log.warning("tds_accept_skipped_no_entity_type", booking_id=str(booking_id))
        return TdsAcceptResult(
            applied=False,
            tds_liability_inr=Decimal("0"),
            tds_collected_online_inr=Decimal("0"),
            amount_due_offline_inr=turnover,
            recovery_pending=False,
            message="Entity type missing — TDS deferred.",
        )

    now = dt.datetime.now(dt.UTC)
    fy_start = fy_start_for_date(now.astimezone(_tz()).date())
    cfg = await load_tds_facilitation_config(db, as_of=now)
    fy_row = await _lock_fy_row(db, pujari_id=pujari_id, fy_start=fy_start)

    accrual = compute_facilitation_accrual(
        entity_type=compliance["entity_type"],
        pan_on_file=bool(compliance["pan_on_file"]),
        fy_gross_before=fy_row["gross_facilitation"],
        this_amount=turnover,
        deduction_latched=fy_row["deduction_latched"],
        config=cfg,
        pan_status=compliance.get("pan_status"),
    )

    collected, order_id, recovery_needed = await attempt_tds_online_collection(
        db, booking_id=booking_id, tds_liability_inr=accrual.tds_amount
    )
    if get_settings().TDS_ACCEPT_STUB_COLLECT and accrual.tds_amount > 0:
        collected = accrual.tds_amount
        recovery_needed = False

    await apply_fy_turnover_and_booking_snapshot(
        db,
        booking_id=booking_id,
        pujari_id=pujari_id,
        fy_start=fy_start,
        turnover_inr=turnover,
        taxable_base_inr=accrual.taxable_base,
        tds_liability_inr=accrual.tds_amount,
        tds_collected_online_inr=collected,
        tds_rate=accrual.rate,
        deduction_latched_after=accrual.deduction_latched_after,
    )

    if recovery_needed and accrual.tds_amount > 0:
        await close_tds_razorpay_order(db, booking_id=booking_id, reason="accept_recovery")
        await ensure_recovery_pending(
            db,
            pujari_id=pujari_id,
            booking_id=booking_id,
            fy_start=fy_start,
            tds_amount=accrual.tds_amount,
        )
        await db.execute(
            text(
                """
                UPDATE bookings
                SET tds_collected_online = 0,
                    amount_due_offline = total_amount,
                    updated_at = now()
                WHERE id = :bid
                """
            ),
            {"bid": str(booking_id)},
        )

    snap = await load_booking_tds_v3_snapshot(db, booking_id=booking_id)
    log.info(
        "tds_applied_at_accept",
        booking_id=str(booking_id),
        pujari_id=str(pujari_id),
        liability=str(accrual.tds_amount),
        collected=str(snap.tds_collected_online_inr),
        recovery=recovery_needed,
        order_id=order_id,
    )
    return TdsAcceptResult(
        applied=True,
        tds_liability_inr=accrual.tds_amount,
        tds_collected_online_inr=snap.tds_collected_online_inr,
        amount_due_offline_inr=(snap.turnover_inr - snap.tds_collected_online_inr).quantize(
            Decimal("0.01")
        ),
        recovery_pending=recovery_needed and accrual.tds_amount > 0,
        tds_razorpay_order_id=order_id,
    )


def _tz() -> dt.tzinfo:
    import zoneinfo

    return zoneinfo.ZoneInfo(get_settings().PLATFORM_TIMEZONE)


async def mark_tds_collected_from_webhook(
    db: AsyncSession,
    *,
    booking_id: uuid.UUID,
    amount_inr: Decimal,
    order_id: str | None = None,
    gateway_txn_id: str = "",
) -> dict[str, str]:
    """Webhook path when TDS Razorpay payment succeeds (idempotent + late-pay guard)."""
    if not gateway_txn_id:
        gateway_txn_id = f"legacy-no-txn-{booking_id}"
    return await handle_tds_payment_webhook(
        db,
        booking_id=booking_id,
        order_id=order_id,
        amount_inr=amount_inr,
        gateway_txn_id=gateway_txn_id,
    )
