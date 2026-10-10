"""TDS v3 — single writer for FY turnover + latch (see TDS_V3_IMPLEMENTATION.md).

Exactly one code path may increment ``pujari_tax_year.gross_facilitation`` and set
``deduction_latched`` per booking — **booking confirmation (accept)** via
``apply_fy_turnover_and_booking_snapshot``.

Balance-collection accrual only materializes the ledger from the booking snapshot.
"""
from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

FY_TURNOVER_INCREMENT_OWNER: str = "booking_confirmation"


@dataclass(frozen=True)
class BookingTdsV3Snapshot:
    turnover_inr: Decimal
    taxable_base_inr: Decimal
    tds_liability_inr: Decimal
    tds_collected_online_inr: Decimal
    tds_rate: Decimal
    fy_applied_at: dt.datetime | None


async def load_booking_tds_v3_snapshot(
    db: AsyncSession, *, booking_id: uuid.UUID
) -> BookingTdsV3Snapshot:
    row = (
        await db.execute(
            text(
                """
                SELECT total_amount,
                       tds_liability_inr,
                       tds_collected_online,
                       tds_rate_applied,
                       tds_taxable_base,
                       tds_facilitation_fy_applied_at
                FROM bookings
                WHERE id = :bid
                """
            ),
            {"bid": str(booking_id)},
        )
    ).mappings().first()
    if row is None:
        raise ValueError("Booking not found for TDS snapshot load.")
    turnover = Decimal(str(row["total_amount"])).quantize(Decimal("0.01"))
    liability = row["tds_liability_inr"]
    collected = row["tds_collected_online"]
    taxable = row["tds_taxable_base"]
    rate = row["tds_rate_applied"]
    return BookingTdsV3Snapshot(
        turnover_inr=turnover,
        taxable_base_inr=Decimal(str(taxable)).quantize(Decimal("0.01"))
        if taxable is not None
        else Decimal("0"),
        tds_liability_inr=Decimal(str(liability)).quantize(Decimal("0.01"))
        if liability is not None
        else Decimal("0"),
        tds_collected_online_inr=Decimal(str(collected)).quantize(Decimal("0.01"))
        if collected is not None
        else Decimal("0"),
        tds_rate=Decimal(str(rate)) if rate is not None else Decimal("0"),
        fy_applied_at=row["tds_facilitation_fy_applied_at"],
    )


async def apply_fy_turnover_and_booking_snapshot(
    db: AsyncSession,
    *,
    booking_id: uuid.UUID,
    pujari_id: uuid.UUID,
    fy_start: dt.date,
    turnover_inr: Decimal,
    taxable_base_inr: Decimal,
    tds_liability_inr: Decimal,
    tds_collected_online_inr: Decimal,
    tds_rate: Decimal,
    deduction_latched_after: bool,
) -> None:
    """Increment FY turnover + latch; persist booking TDS snapshot. Single writer per booking."""
    turnover = turnover_inr.quantize(Decimal("0.01"))
    taxable = taxable_base_inr.quantize(Decimal("0.01"))
    liability = tds_liability_inr.quantize(Decimal("0.01"))
    collected = tds_collected_online_inr.quantize(Decimal("0.01"))
    # Offline due tracks collected TDS only — not liability (recovery path keeps full cash offline).
    offline = (turnover - collected).quantize(Decimal("0.01"))
    await db.execute(
        text(
            """
            UPDATE pujari_tax_year
            SET gross_facilitation = gross_facilitation + :turnover,
                tds_accrued = tds_accrued + :liability,
                deduction_latched = deduction_latched OR :latched,
                updated_at = now()
            WHERE pujari_id = :pid AND fy_start = :fy
            """
        ),
        {
            "turnover": str(turnover),
            "liability": str(liability),
            "latched": deduction_latched_after,
            "pid": str(pujari_id),
            "fy": fy_start,
        },
    )
    await db.execute(
        text(
            """
            UPDATE bookings
            SET tds_liability_inr = :liability,
                tds_collected_online = :collected,
                tds_rate_applied = :rate,
                tds_taxable_base = :taxable,
                amount_due_offline = :offline,
                tds_facilitation_fy_applied_at = COALESCE(
                    tds_facilitation_fy_applied_at, now()
                ),
                updated_at = now()
            WHERE id = :bid
              AND tds_facilitation_fy_applied_at IS NULL
            """
        ),
        {
            "bid": str(booking_id),
            "liability": str(liability),
            "collected": str(collected),
            "rate": str(tds_rate),
            "taxable": str(taxable),
            "offline": str(offline),
        },
    )


async def update_tds_collected_online(
    db: AsyncSession,
    *,
    booking_id: uuid.UUID,
    tds_collected_online_inr: Decimal,
) -> None:
    """After successful Razorpay TDS capture — sync offline due with collected TDS."""
    snap = await load_booking_tds_v3_snapshot(db, booking_id=booking_id)
    collected = tds_collected_online_inr.quantize(Decimal("0.01"))
    offline = (snap.turnover_inr - collected).quantize(Decimal("0.01"))
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
        {"bid": str(booking_id), "collected": str(collected), "offline": str(offline)},
    )


async def insert_facilitation_accrual_ledger(
    db: AsyncSession,
    *,
    pujari_id: uuid.UUID,
    booking_id: uuid.UUID,
    fy_start: dt.date,
    ledger_taxable_base: Decimal,
    tds_amount: Decimal,
) -> None:
    """Append accrual row; ``gross_amount`` is taxable base (not FY turnover)."""
    await db.execute(
        text(
            """
            INSERT INTO pujari_tds_facilitation_ledger (
                id, pujari_id, booking_id, entry_type, gross_amount, tds_amount, fy_start
            ) VALUES (
                gen_random_uuid(), :pid, :bid, 'accrual', :gross, :tds, :fy
            )
            """
        ),
        {
            "pid": str(pujari_id),
            "bid": str(booking_id),
            "gross": str(ledger_taxable_base.quantize(Decimal("0.01"))),
            "tds": str(tds_amount.quantize(Decimal("0.01"))),
            "fy": fy_start,
        },
    )
