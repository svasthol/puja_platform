"""TDS v7 — proportional facilitation reversal (FY, ledger, recovery, online refund)."""
from __future__ import annotations

import datetime as dt
import uuid
import zoneinfo
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.payment import Refund
from app.services.pricing_tds_v3 import reverse_facilitation
from app.services.tds_accrual_service import _lock_fy_row, _read_fy_row, fy_start_for_date
from app.services.tds_v3_fy_writer import load_booking_tds_v3_snapshot
from app.services.tds_v3_online_charge import close_tds_razorpay_order

log = structlog.get_logger()
_PAISE = Decimal("0.01")


@dataclass(frozen=True)
class FacilitationRemaining:
    turnover_inr: Decimal
    taxable_base_inr: Decimal
    tds_liability_inr: Decimal


@dataclass(frozen=True)
class ReversalSliceApplied:
    turnover_reversal: Decimal
    taxable_base_reversal: Decimal
    tds_reversal: Decimal


async def _ledger_refund_reference_exists(
    db: AsyncSession, *, refund_reference: str
) -> bool:
    row = (
        await db.execute(
            text(
                """
                SELECT 1 FROM pujari_tds_facilitation_ledger
                WHERE entry_type = 'reversal'
                  AND refund_reference = :ref
                """
            ),
            {"ref": refund_reference},
        )
    ).scalar_one_or_none()
    return row is not None


async def _sum_prior_reversals(
    db: AsyncSession, *, booking_id: uuid.UUID
) -> tuple[Decimal, Decimal]:
    row = (
        await db.execute(
            text(
                """
                SELECT COALESCE(SUM(gross_amount), 0) AS taxable_rev,
                       COALESCE(SUM(tds_amount), 0) AS tds_rev
                FROM pujari_tds_facilitation_ledger
                WHERE booking_id = :bid AND entry_type = 'reversal'
                """
            ),
            {"bid": str(booking_id)},
        )
    ).mappings().first()
    return (
        Decimal(str(row["taxable_rev"])).quantize(_PAISE),
        Decimal(str(row["tds_rev"])).quantize(_PAISE),
    )


async def facilitation_remaining(
    db: AsyncSession, *, booking_id: uuid.UUID
) -> FacilitationRemaining | None:
    """Remaining facilitation after prior reversals (booking columns are live remainder)."""
    snap = await load_booking_tds_v3_snapshot(db, booking_id=booking_id)
    if snap.fy_applied_at is None:
        return None
    taxable_rev, tds_rev = await _sum_prior_reversals(db, booking_id=booking_id)
    cur_taxable = snap.taxable_base_inr
    cur_tds = snap.tds_liability_inr
    taxable_at_accept = (cur_taxable + taxable_rev).quantize(_PAISE)
    tds_at_accept = (cur_tds + tds_rev).quantize(_PAISE)
    turnover_booking = snap.turnover_inr
    if taxable_at_accept > 0:
        turnover_rem = (
            turnover_booking * cur_taxable / taxable_at_accept
        ).quantize(_PAISE)
    elif tds_at_accept > 0:
        turnover_rem = (turnover_booking * cur_tds / tds_at_accept).quantize(_PAISE)
    else:
        turnover_rem = Decimal("0")
    return FacilitationRemaining(
        turnover_inr=max(Decimal("0"), turnover_rem),
        taxable_base_inr=max(Decimal("0"), cur_taxable),
        tds_liability_inr=max(Decimal("0"), cur_tds),
    )


def _cap_reversal_slice(
    *,
    ideal: ReversalSliceApplied,
    remaining: FacilitationRemaining,
) -> ReversalSliceApplied:
    return ReversalSliceApplied(
        turnover_reversal=min(ideal.turnover_reversal, remaining.turnover_inr),
        taxable_base_reversal=min(ideal.taxable_base_reversal, remaining.taxable_base_inr),
        tds_reversal=min(ideal.tds_reversal, remaining.tds_liability_inr),
    )


async def _resolve_fy_start_for_booking(
    db: AsyncSession, *, booking_id: uuid.UUID, pujari_id: uuid.UUID
) -> dt.date | None:
    accrual = (
        await db.execute(
            text(
                """
                SELECT fy_start FROM pujari_tds_facilitation_ledger
                WHERE booking_id = :bid AND entry_type = 'accrual'
                """
            ),
            {"bid": str(booking_id)},
        )
    ).scalar_one_or_none()
    if accrual is not None:
        return accrual if isinstance(accrual, dt.date) else accrual.date()
    snap = await load_booking_tds_v3_snapshot(db, booking_id=booking_id)
    if snap.fy_applied_at is None:
        return None
    applied = snap.fy_applied_at
    if applied.tzinfo is None:
        applied = applied.replace(tzinfo=dt.UTC)
    return fy_start_for_date(applied.date())


async def _cancel_accrual_intents(db: AsyncSession, *, booking_id: uuid.UUID) -> None:
    await db.execute(
        text(
            """
            UPDATE pujari_tds_accrual_intents
            SET status = 'cancelled',
                park_reason = COALESCE(park_reason, 'facilitation_reversed'),
                processed_at = now()
            WHERE booking_id = :bid
              AND status IN ('pending', 'parked', 'processing')
            """
        ),
        {"bid": str(booking_id)},
    )


async def _find_tds_payment_id(
    db: AsyncSession, *, booking_id: uuid.UUID
) -> uuid.UUID | None:
    row = (
        await db.execute(
            text(
                """
                SELECT id FROM payments
                WHERE booking_id = :bid
                  AND status = 'success'
                  AND idempotency_key LIKE 'tds:%'
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"bid": str(booking_id)},
        )
    ).scalar_one_or_none()
    return uuid.UUID(str(row)) if row else None


async def _route_tds_money_on_reversal(
    db: AsyncSession,
    *,
    booking_id: uuid.UUID,
    reversed_tds: Decimal,
    tds_collected_online: Decimal,
    tds_liability: Decimal,
    refund_reference: str,
) -> dict[str, Any]:
    if reversed_tds <= 0:
        return {"customer_refund_inr": "0", "recovery_adjusted_inr": "0"}

    liability = tds_liability.quantize(_PAISE)
    collected = tds_collected_online.quantize(_PAISE)
    recovery_row = (
        await db.execute(
            text(
                """
                SELECT id, tds_amount, status
                FROM pujari_tds_recovery
                WHERE booking_id = :bid
                """
            ),
            {"bid": str(booking_id)},
        )
    ).mappings().first()

    recovery_pending = Decimal("0")
    if recovery_row and recovery_row["status"] == "pending":
        recovery_pending = Decimal(str(recovery_row["tds_amount"])).quantize(_PAISE)

    if liability > 0:
        online_share = (reversed_tds * collected / liability).quantize(_PAISE)
        recovery_share = (reversed_tds * recovery_pending / liability).quantize(_PAISE)
    else:
        online_share = Decimal("0")
        recovery_share = Decimal("0")

    online_share = min(online_share, collected, reversed_tds)
    recovery_share = min(recovery_share, recovery_pending, reversed_tds - online_share)
    remainder = reversed_tds - online_share - recovery_share
    if remainder > 0 and collected > online_share:
        online_share += min(remainder, collected - online_share)
        remainder = reversed_tds - online_share - recovery_share
    if remainder > 0 and recovery_pending > recovery_share:
        recovery_share += min(remainder, recovery_pending - recovery_share)

    customer_refund = online_share
    if customer_refund > 0:
        payment_id = await _find_tds_payment_id(db, booking_id=booking_id)
        if payment_id is not None:
            active = (
                await db.execute(
                    text(
                        """
                        SELECT id, amount FROM refunds
                        WHERE payment_id = :pid
                          AND status IN ('pending', 'processing')
                        ORDER BY created_at DESC
                        LIMIT 1
                        """
                    ),
                    {"pid": str(payment_id)},
                )
            ).mappings().first()
            if active is not None:
                new_amt = Decimal(str(active["amount"])) + customer_refund
                await db.execute(
                    text(
                        """
                        UPDATE refunds
                        SET amount = :amt
                        WHERE id = :rid
                        """
                    ),
                    {"rid": str(active["id"]), "amt": str(new_amt.quantize(_PAISE))},
                )
            else:
                db.add(
                    Refund(
                        id=uuid.uuid4(),
                        payment_id=payment_id,
                        booking_id=booking_id,
                        amount=float(customer_refund),
                        reason="tds_facilitation_reversal",
                        status="pending",
                        attempt_count=0,
                        next_attempt_at=dt.datetime.now(dt.UTC),
                        created_at=dt.datetime.now(dt.UTC),
                    )
                )
        new_collected = max(Decimal("0"), collected - customer_refund).quantize(_PAISE)
        turnover_row = (
            await db.execute(
                text("SELECT total_amount FROM bookings WHERE id = :bid"),
                {"bid": str(booking_id)},
            )
        ).scalar_one()
        turnover = Decimal(str(turnover_row)).quantize(_PAISE)
        await db.execute(
            text(
                """
                UPDATE bookings
                SET tds_collected_online = :collected,
                    amount_due_offline = :offline,
                    updated_at = now()
                WHERE id = :bid
                """
            ),
            {
                "bid": str(booking_id),
                "collected": str(new_collected),
                "offline": str((turnover - new_collected).quantize(_PAISE)),
            },
        )

    if recovery_share > 0 and recovery_row:
        new_recovery = (recovery_pending - recovery_share).quantize(_PAISE)
        if new_recovery <= 0:
            await db.execute(
                text(
                    """
                    UPDATE pujari_tds_recovery
                    SET status = 'void',
                        recovered_at = now(),
                        recovery_ref = :ref
                    WHERE booking_id = :bid
                    """
                ),
                {"bid": str(booking_id), "ref": refund_reference[:100]},
            )
        else:
            await db.execute(
                text(
                    """
                    UPDATE pujari_tds_recovery
                    SET tds_amount = :amt,
                        recovery_ref = :ref
                    WHERE booking_id = :bid AND status = 'pending'
                    """
                ),
                {
                    "bid": str(booking_id),
                    "amt": str(new_recovery),
                    "ref": refund_reference[:100],
                },
            )
    elif (
        recovery_row
        and recovery_row["status"] == "pending"
        and reversed_tds >= recovery_pending
        and recovery_pending > 0
    ):
        await db.execute(
            text(
                """
                UPDATE pujari_tds_recovery
                SET status = 'void',
                    recovered_at = now(),
                    recovery_ref = :ref
                WHERE booking_id = :bid
                """
            ),
            {"bid": str(booking_id), "ref": refund_reference[:100]},
        )

    return {
        "customer_refund_inr": str(customer_refund),
        "recovery_adjusted_inr": str(recovery_share),
    }


async def apply_facilitation_reversal(
    db: AsyncSession,
    *,
    booking_id: uuid.UUID,
    pujari_id: uuid.UUID,
    refund_reference: str,
    refund_fraction: Decimal,
) -> dict[str, Any]:
    """T7 proportional reversal — idempotent on ``refund_reference``."""
    ref = refund_reference.strip()
    if not ref:
        raise ValueError("refund_reference required")
    frac = refund_fraction.quantize(Decimal("0.0001"))
    if frac <= 0 or frac > 1:
        raise ValueError("refund_fraction must be in (0, 1]")

    if await _ledger_refund_reference_exists(db, refund_reference=ref):
        return {
            "reversed": False,
            "idempotent": True,
            "reason": "refund_reference already applied",
            "booking_id": str(booking_id),
            "refund_reference": ref,
        }

    await db.execute(
        text("SELECT id FROM bookings WHERE id = :bid FOR UPDATE"),
        {"bid": str(booking_id)},
    )

    snap = await load_booking_tds_v3_snapshot(db, booking_id=booking_id)
    if snap.fy_applied_at is None:
        return {
            "reversed": False,
            "reason": "TDS FY snapshot not applied at accept",
            "booking_id": str(booking_id),
        }

    await close_tds_razorpay_order(db, booking_id=booking_id, reason="facilitation_reversal")

    remaining = await facilitation_remaining(db, booking_id=booking_id)
    if remaining is None or (
        remaining.turnover_inr <= 0 and remaining.tds_liability_inr <= 0
    ):
        return {
            "reversed": False,
            "reason": "Nothing left to reverse",
            "booking_id": str(booking_id),
            "refund_reference": ref,
        }

    taxable_rev, tds_rev = await _sum_prior_reversals(db, booking_id=booking_id)
    orig_turnover = snap.turnover_inr
    orig_taxable = (snap.taxable_base_inr + taxable_rev).quantize(_PAISE)
    orig_tds = (snap.tds_liability_inr + tds_rev).quantize(_PAISE)

    ideal_raw = reverse_facilitation(
        booking_turnover=orig_turnover,
        ledger_taxable_base=orig_taxable,
        ledger_tds_amount=orig_tds,
        refund_fraction=frac,
    )
    ideal = ReversalSliceApplied(
        turnover_reversal=ideal_raw.turnover_reversal,
        taxable_base_reversal=ideal_raw.taxable_base_reversal,
        tds_reversal=ideal_raw.tds_reversal,
    )
    applied = _cap_reversal_slice(ideal=ideal, remaining=remaining)

    if (
        applied.turnover_reversal <= 0
        and applied.tds_reversal <= 0
        and applied.taxable_base_reversal <= 0
    ):
        return {
            "reversed": False,
            "reason": "Cumulative cap — no remainder",
            "booking_id": str(booking_id),
            "refund_reference": ref,
        }

    fy_start = await _resolve_fy_start_for_booking(
        db, booking_id=booking_id, pujari_id=pujari_id
    )
    if fy_start is None:
        return {"reversed": False, "reason": "FY start unknown", "booking_id": str(booking_id)}

    fy_locked = await _lock_fy_row(db, pujari_id=pujari_id, fy_start=fy_start)
    latched_before = fy_locked["deduction_latched"]

    await db.execute(
        text(
            """
            UPDATE pujari_tax_year
            SET gross_facilitation = GREATEST(0, gross_facilitation - :turnover),
                tds_accrued = GREATEST(0, tds_accrued - :tds),
                updated_at = now()
            WHERE pujari_id = :pid AND fy_start = :fy
            """
        ),
        {
            "turnover": str(applied.turnover_reversal),
            "tds": str(applied.tds_reversal),
            "pid": str(pujari_id),
            "fy": fy_start,
        },
    )
    latched_after = (
        await _read_fy_row(db, pujari_id=pujari_id, fy_start=fy_start)
    )["deduction_latched"]
    if latched_after != latched_before:
        log.error(
            "tds_reversal_latch_mutation",
            booking_id=str(booking_id),
            before=latched_before,
            after=latched_after,
        )

    try:
        await db.execute(
            text(
                """
                INSERT INTO pujari_tds_facilitation_ledger (
                    id, pujari_id, booking_id, entry_type,
                    gross_amount, tds_amount, fy_start, refund_reference
                ) VALUES (
                    gen_random_uuid(), :pid, :bid, 'reversal',
                    :gross, :tds, :fy, :ref
                )
                """
            ),
            {
                "pid": str(pujari_id),
                "bid": str(booking_id),
                "gross": str(applied.taxable_base_reversal),
                "tds": str(applied.tds_reversal),
                "fy": fy_start,
                "ref": ref,
            },
        )
    except IntegrityError:
        return {
            "reversed": False,
            "idempotent": True,
            "reason": "refund_reference race",
            "booking_id": str(booking_id),
            "refund_reference": ref,
        }

    await db.execute(
        text(
            """
            UPDATE bookings
            SET tds_liability_inr = GREATEST(
                    0, COALESCE(tds_liability_inr, 0) - :tds
                ),
                tds_taxable_base = GREATEST(
                    0, COALESCE(tds_taxable_base, 0) - :taxable
                ),
                updated_at = now()
            WHERE id = :bid
            """
        ),
        {
            "bid": str(booking_id),
            "tds": str(applied.tds_reversal),
            "taxable": str(applied.taxable_base_reversal),
        },
    )

    money = await _route_tds_money_on_reversal(
        db,
        booking_id=booking_id,
        reversed_tds=applied.tds_reversal,
        tds_collected_online=snap.tds_collected_online_inr,
        tds_liability=orig_tds,
        refund_reference=ref,
    )
    await _cancel_accrual_intents(db, booking_id=booking_id)

    log.info(
        "tds_facilitation_reversed",
        booking_id=str(booking_id),
        refund_reference=ref,
        fraction=str(frac),
        turnover=str(applied.turnover_reversal),
        tds=str(applied.tds_reversal),
    )
    return {
        "reversed": True,
        "booking_id": str(booking_id),
        "refund_reference": ref,
        "refund_fraction": str(frac),
        "turnover_reversed_inr": str(applied.turnover_reversal),
        "taxable_base_reversed_inr": str(applied.taxable_base_reversal),
        "tds_reversed_inr": str(applied.tds_reversal),
        "fy_start": fy_start.isoformat(),
        "deduction_latched_unchanged": latched_after == latched_before,
        "tds_deposit_credit_note": (
            "Cross-FY deposited TDS: carry credit / 26Q adjustment (Phase 3); no challan claw."
            if applied.tds_reversal > 0
            else None
        ),
        **money,
    }


async def sweep_never_collected_facilitation(
    db: AsyncSession,
    *,
    limit: int = 50,
    grace_hours_after_scheduled: int = 24,
) -> dict[str, int]:
    """No-show / expiry — full reversal when FY applied but balance never collected."""
    tz = zoneinfo.ZoneInfo(get_settings().PLATFORM_TIMEZONE)
    rows = (
        await db.execute(
            text(
                """
                SELECT b.id AS booking_id, b.pujari_id,
                       b.scheduled_date, b.scheduled_time
                FROM bookings b
                JOIN status_types st ON st.id = b.status_id
                WHERE b.tds_facilitation_fy_applied_at IS NOT NULL
                  AND b.balance_collected_at IS NULL
                  AND b.cancelled_at IS NULL
                  AND b.pujari_id IS NOT NULL
                  AND st.code IN ('confirmed', 'in_progress')
                ORDER BY b.scheduled_date
                LIMIT :lim
                """
            ),
            {"lim": limit},
        )
    ).mappings().all()

    now_local = dt.datetime.now(dt.UTC).astimezone(tz)
    reversed_count = skipped = 0
    for row in rows:
        scheduled = dt.datetime.combine(
            row["scheduled_date"], row["scheduled_time"], tzinfo=tz
        )
        if (now_local - scheduled).total_seconds() < grace_hours_after_scheduled * 3600:
            skipped += 1
            continue
        bid = uuid.UUID(str(row["booking_id"]))
        pid = uuid.UUID(str(row["pujari_id"]))
        outcome = await apply_facilitation_reversal(
            db,
            booking_id=bid,
            pujari_id=pid,
            refund_reference=f"no_show:{bid}",
            refund_fraction=Decimal("1"),
        )
        if outcome.get("reversed"):
            reversed_count += 1
        else:
            skipped += 1
    return {"reversed": reversed_count, "skipped": skipped}
