"""
TDS facilitation accrual at confirm-balance-collected (Sprint 2 / P-TDS-393).

Per-pujari FY gross tracked in pujari_tax_year (FOR UPDATE at accrual).
Append-only ledger in pujari_tds_facilitation_ledger; one accrual per booking.
"""
from __future__ import annotations

import datetime as dt
import uuid
import zoneinfo
from decimal import Decimal
from typing import Any

import structlog
from fastapi import HTTPException, status as http
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.pricing import load_tds_facilitation_config
from app.services.tds_v3_fy_writer import (
    insert_facilitation_accrual_ledger,
    load_booking_tds_v3_snapshot,
)

log = structlog.get_logger()

# Worker batch bounds (D6 — outer pujari cap + inner intent cap per tick)
_DEFAULT_PUJARI_BATCH_LIMIT = 50
_DEFAULT_INTENTS_PER_PUJARI = 25


def _tz() -> zoneinfo.ZoneInfo:
    return zoneinfo.ZoneInfo(get_settings().PLATFORM_TIMEZONE)


def _accrual_enabled() -> bool:
    return get_settings().TDS_ACCRUAL_ENABLED


def fy_start_for_date(d: dt.date) -> dt.date:
    """Indian FY start (April–March) for a calendar date."""
    if d.month >= 4:
        return dt.date(d.year, 4, 1)
    return dt.date(d.year - 1, 4, 1)


def _format_rate(rate: Decimal) -> str:
    return format(rate.normalize(), "f")


async def _pujari_compliance(db: AsyncSession, pujari_id: uuid.UUID) -> dict[str, Any]:
    row = (
        await db.execute(
            text(
                """
                SELECT entity_type,
                       pan_hash IS NOT NULL AS pan_on_file,
                       pan_status
                FROM pujaris
                WHERE id = :pid
                """
            ),
            {"pid": str(pujari_id)},
        )
    ).mappings().first()
    if row is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "Pujari not found.")
    return dict(row)


async def lookup_classification_snapshot_for_booking(
    db: AsyncSession, booking_id: uuid.UUID
) -> dict[str, Any] | None:
    """Point-in-time entity_type + PAN-presence frozen at balance collection (§0.L-4)."""
    row = (
        await db.execute(
            text(
                """
                SELECT tds_snapshot_entity_type AS entity_type,
                       tds_snapshot_pan_on_file AS pan_on_file,
                       balance_collected_at
                FROM bookings
                WHERE id = :bid
                """
            ),
            {"bid": str(booking_id)},
        )
    ).mappings().first()
    if row is None or row["balance_collected_at"] is None:
        return None
    if row["pan_on_file"] is None:
        return None
    return {
        "entity_type": row["entity_type"],
        "pan_on_file": bool(row["pan_on_file"]),
    }


async def capture_classification_snapshot_at_collection(
    db: AsyncSession,
    *,
    booking_id: uuid.UUID,
    pujari_id: uuid.UUID,
) -> bool:
    """Persist §0.L-4 snapshot. Fail-open — logs and returns False; never blocks collection."""
    try:
        row = (
            await db.execute(
                text(
                    """
                    SELECT entity_type, pan_hash IS NOT NULL AS pan_on_file
                    FROM pujaris
                    WHERE id = :pid
                    """
                ),
                {"pid": str(pujari_id)},
            )
        ).mappings().first()
        if row is None:
            log.warning(
                "tds_classification_snapshot_skipped",
                booking_id=str(booking_id),
                reason="pujari_not_found",
            )
            return False
        result = await db.execute(
            text(
                """
                UPDATE bookings
                SET tds_snapshot_entity_type = :et,
                    tds_snapshot_pan_on_file = :pan,
                    updated_at = now()
                WHERE id = :bid
                  AND balance_collected_at IS NOT NULL
                  AND tds_snapshot_pan_on_file IS NULL
                """
            ),
            {
                "et": row["entity_type"],
                "pan": bool(row["pan_on_file"]),
                "bid": str(booking_id),
            },
        )
        return result.rowcount > 0
    except Exception as exc:
        log.warning(
            "tds_classification_snapshot_failed",
            booking_id=str(booking_id),
            error=str(exc),
        )
        return False


async def _read_fy_row(
    db: AsyncSession, *, pujari_id: uuid.UUID, fy_start: dt.date
) -> dict[str, Any]:
    row = (
        await db.execute(
            text(
                """
                SELECT gross_facilitation, tds_accrued, deduction_latched
                FROM pujari_tax_year
                WHERE pujari_id = :pid AND fy_start = :fy
                """
            ),
            {"pid": str(pujari_id), "fy": fy_start},
        )
    ).mappings().first()
    if row is None:
        return {
            "gross_facilitation": Decimal("0"),
            "tds_accrued": Decimal("0"),
            "deduction_latched": False,
        }
    return {
        "gross_facilitation": Decimal(str(row["gross_facilitation"])),
        "tds_accrued": Decimal(str(row["tds_accrued"])),
        "deduction_latched": bool(row["deduction_latched"]),
    }


async def _lock_fy_row(
    db: AsyncSession, *, pujari_id: uuid.UUID, fy_start: dt.date
) -> dict[str, Any]:
    await db.execute(
        text(
            """
            INSERT INTO pujari_tax_year (pujari_id, fy_start, gross_facilitation, tds_accrued)
            VALUES (:pid, :fy, 0, 0)
            ON CONFLICT (pujari_id, fy_start) DO NOTHING
            """
        ),
        {"pid": str(pujari_id), "fy": fy_start},
    )
    row = (
        await db.execute(
            text(
                """
                SELECT gross_facilitation, tds_accrued, deduction_latched
                FROM pujari_tax_year
                WHERE pujari_id = :pid AND fy_start = :fy
                FOR UPDATE
                """
            ),
            {"pid": str(pujari_id), "fy": fy_start},
        )
    ).mappings().first()
    if row is None:
        raise HTTPException(http.HTTP_500_INTERNAL_SERVER_ERROR, "FY tax row missing after upsert.")
    return {
        "gross_facilitation": Decimal(str(row["gross_facilitation"])),
        "tds_accrued": Decimal(str(row["tds_accrued"])),
        "deduction_latched": bool(row["deduction_latched"]),
    }


async def tds_snapshot_for_booking(
    db: AsyncSession, *, booking_id: uuid.UUID, pujari_id: uuid.UUID
) -> dict[str, Any]:
    """TDS block for confirm-balance response (collected or already_collected)."""
    if not _accrual_enabled():
        return _tds_payload(
            accrual_enabled=False,
            skipped=True,
            message="TDS accrual disabled (launch default).",
        )
    existing = await lookup_accrual_for_booking(db, booking_id)
    if existing is None:
        return _tds_payload(
            accrual_enabled=True,
            skipped=True,
            message="No TDS accrual recorded for this booking.",
        )
    cfg = await load_tds_facilitation_config(db)
    fy_row = await _read_fy_row(
        db, pujari_id=pujari_id, fy_start=existing["fy_start"]
    )
    return _tds_payload(
        accrual_enabled=True,
        skipped=False,
        idempotent=True,
        tds_rate=Decimal(existing["tds_rate"]),
        tds_amount=existing["tds_amount"],
        fy_gross_after=fy_row["gross_facilitation"],
        fy_threshold_inr=cfg.individual_fy_threshold_inr,
    )


async def lookup_accrual_intent(
    db: AsyncSession, booking_id: uuid.UUID
) -> dict[str, Any] | None:
    row = (
        await db.execute(
            text(
                """
                SELECT status, park_reason, gross_amount, collected_at
                FROM pujari_tds_accrual_intents
                WHERE booking_id = :bid
                """
            ),
            {"bid": str(booking_id)},
        )
    ).mappings().first()
    return dict(row) if row else None


async def lookup_accrual_for_booking(
    db: AsyncSession, booking_id: uuid.UUID
) -> dict[str, Any] | None:
    row = (
        await db.execute(
            text(
                """
                SELECT gross_amount, tds_amount, fy_start
                FROM pujari_tds_facilitation_ledger
                WHERE booking_id = :bid AND entry_type = 'accrual'
                """
            ),
            {"bid": str(booking_id)},
        )
    ).mappings().first()
    if row is None:
        return None
    gross = Decimal(str(row["gross_amount"]))
    tds = Decimal(str(row["tds_amount"]))
    if gross > 0:
        rate = (tds / gross).quantize(Decimal("0.0001"))
    else:
        rate = Decimal("0")
    return {
        "accrual_enabled": True,
        "skipped": False,
        "idempotent": True,
        "tds_rate": _format_rate(rate),
        "tds_amount": tds,
        "gross_amount": gross,
        "fy_start": row["fy_start"],
    }


def _tds_payload(
    *,
    accrual_enabled: bool,
    skipped: bool,
    idempotent: bool = False,
    tds_rate: Decimal | None = None,
    tds_amount: Decimal | None = None,
    fy_gross_after: Decimal | None = None,
    fy_threshold_inr: Decimal | None = None,
    message: str | None = None,
) -> dict[str, Any]:
    threshold_remaining = None
    if fy_gross_after is not None and fy_threshold_inr is not None:
        threshold_remaining = max(
            Decimal("0"), (fy_threshold_inr - fy_gross_after).quantize(Decimal("0.01"))
        )
    return {
        "accrual_enabled": accrual_enabled,
        "skipped": skipped,
        "idempotent": idempotent,
        "tds_rate": _format_rate(tds_rate) if tds_rate is not None else None,
        "tds_amount": str(tds_amount.quantize(Decimal("0.01"))) if tds_amount is not None else None,
        "fy_gross_after": str(fy_gross_after.quantize(Decimal("0.01")))
        if fy_gross_after is not None
        else None,
        "fy_threshold_inr": str(fy_threshold_inr.quantize(Decimal("0.01")))
        if fy_threshold_inr is not None
        else None,
        "threshold_remaining_inr": str(threshold_remaining) if threshold_remaining is not None else None,
        "message": message,
    }


async def _compliance_from_snapshot_or_live(
    db: AsyncSession,
    *,
    booking_id: uuid.UUID,
    pujari_id: uuid.UUID,
) -> dict[str, Any]:
    snap = await lookup_classification_snapshot_for_booking(db, booking_id)
    if snap is not None:
        live = await _pujari_compliance(db, pujari_id)
        return {
            "entity_type": snap["entity_type"],
            "pan_on_file": snap["pan_on_file"],
            "pan_status": live.get("pan_status"),
        }
    return await _pujari_compliance(db, pujari_id)


async def _execute_accrual(
    db: AsyncSession,
    *,
    booking_id: uuid.UUID,
    pujari_id: uuid.UUID,
    gross_amount: Decimal,
    collected_at: dt.datetime,
    compliance: dict[str, Any],
) -> dict[str, Any]:
    """Materialize ledger from booking TDS snapshot; FY increment is single-writer (v3).

    Pre-T6: if ``tds_facilitation_fy_applied_at`` is unset, compute under FY lock,
    call ``apply_fy_turnover_and_booking_snapshot``, then insert ledger.

    Post-T6: confirmation sets snapshot + FY increment; this path only inserts ledger.
    """
    entity_type = compliance["entity_type"]
    if entity_type is None:
        raise ValueError("entity_type required for TDS accrual")

    when = collected_at.astimezone(_tz())
    fy_start = fy_start_for_date(when.date())
    cfg = await load_tds_facilitation_config(db, as_of=collected_at)

    await db.execute(
        text("SELECT id FROM bookings WHERE id = :bid FOR UPDATE"),
        {"bid": str(booking_id)},
    )
    fy_row = await _lock_fy_row(db, pujari_id=pujari_id, fy_start=fy_start)
    turnover = gross_amount.quantize(Decimal("0.01"))

    existing_ledger = await lookup_accrual_for_booking(db, booking_id)
    if existing_ledger is not None:
        return _tds_payload(
            accrual_enabled=True,
            skipped=False,
            idempotent=True,
            tds_rate=Decimal(existing_ledger["tds_rate"]),
            tds_amount=existing_ledger["tds_amount"],
            fy_gross_after=fy_row["gross_facilitation"],
            fy_threshold_inr=cfg.individual_fy_threshold_inr,
        )

    booking_snap = await load_booking_tds_v3_snapshot(db, booking_id=booking_id)
    if booking_snap.fy_applied_at is None:
        raise ValueError(
            "TDS FY snapshot missing — run apply_tds_at_booking_confirmation at accept before accrual."
        )

    from app.services.tds_v3_reversal_service import _sum_prior_reversals

    _, tds_rev_prior = await _sum_prior_reversals(db, booking_id=booking_id)
    if tds_rev_prior > 0 and booking_snap.tds_liability_inr <= 0:
        raise ValueError("TDS facilitation fully reversed — accrual blocked.")

    taxable = booking_snap.taxable_base_inr
    tds_amount = booking_snap.tds_liability_inr
    rate = booking_snap.tds_rate

    await insert_facilitation_accrual_ledger(
        db,
        pujari_id=pujari_id,
        booking_id=booking_id,
        fy_start=fy_start,
        ledger_taxable_base=taxable,
        tds_amount=tds_amount,
    )

    fy_after = (
        await _read_fy_row(db, pujari_id=pujari_id, fy_start=fy_start)
    )["gross_facilitation"]
    log.info(
        "tds_accrued",
        booking_id=str(booking_id),
        pujari_id=str(pujari_id),
        turnover=str(turnover),
        taxable_base=str(taxable),
        tds=str(tds_amount),
        fy_start=str(fy_start),
        ledger_only=True,
    )
    return _tds_payload(
        accrual_enabled=True,
        skipped=False,
        idempotent=False,
        tds_rate=rate,
        tds_amount=tds_amount,
        fy_gross_after=fy_after,
        fy_threshold_inr=cfg.individual_fy_threshold_inr,
    )


async def enqueue_tds_accrual_intent(
    db: AsyncSession,
    *,
    booking_id: uuid.UUID,
    pujari_id: uuid.UUID,
    gross_amount: Decimal,
    collected_at: dt.datetime | None = None,
) -> dict[str, Any]:
    """Decouple accrual from confirm-balance critical path (D1)."""
    if not _accrual_enabled():
        return _tds_payload(
            accrual_enabled=False,
            skipped=True,
            message="TDS accrual disabled (launch default).",
        )

    existing = await lookup_accrual_for_booking(db, booking_id)
    if existing is not None:
        cfg = await load_tds_facilitation_config(db)
        fy_row = await _read_fy_row(
            db, pujari_id=pujari_id, fy_start=existing["fy_start"]
        )
        return _tds_payload(
            accrual_enabled=True,
            skipped=False,
            idempotent=True,
            tds_rate=Decimal(existing["tds_rate"]),
            tds_amount=existing["tds_amount"],
            fy_gross_after=fy_row["gross_facilitation"],
            fy_threshold_inr=cfg.individual_fy_threshold_inr,
        )

    when = collected_at or dt.datetime.now(dt.UTC)
    snap = await lookup_classification_snapshot_for_booking(db, booking_id)
    entity_type = snap["entity_type"] if snap else None
    pan_on_file = snap["pan_on_file"] if snap else None
    status = "parked" if entity_type is None else "pending"
    park_reason = "entity_type_missing" if entity_type is None else None

    existing_intent = await lookup_accrual_intent(db, booking_id)
    if existing_intent is not None:
        if existing_intent["status"] == "parked":
            return _tds_payload(
                accrual_enabled=True,
                skipped=True,
                message="TDS accrual parked — entity type missing at collection.",
            )
        return _tds_payload(
            accrual_enabled=True,
            skipped=True,
            message="TDS accrual queued.",
        )

    await db.execute(
            text(
                """
                INSERT INTO pujari_tds_accrual_intents (
                    booking_id, pujari_id, gross_amount, collected_at,
                    snapshot_entity_type, snapshot_pan_on_file,
                    status, park_reason
                ) VALUES (
                    :bid, :pid, :gross, :collected,
                    :et, :pan, :status, :reason
                )
                """
            ),
            {
                "bid": str(booking_id),
                "pid": str(pujari_id),
                "gross": str(gross_amount.quantize(Decimal("0.01"))),
                "collected": when,
                "et": entity_type,
                "pan": pan_on_file,
                "status": status,
                "reason": park_reason,
            },
        )

    if status == "parked":
        return _tds_payload(
            accrual_enabled=True,
            skipped=True,
            message="TDS accrual parked — entity type missing at collection.",
        )
    return _tds_payload(
        accrual_enabled=True,
        skipped=True,
        message="TDS accrual queued.",
    )


async def _mark_intent_status(
    db: AsyncSession,
    *,
    intent_id: uuid.UUID,
    status: str,
    park_reason: str | None = None,
    last_error: str | None = None,
    increment_attempt: bool = False,
) -> None:
    if increment_attempt:
        await db.execute(
            text(
                """
                UPDATE pujari_tds_accrual_intents
                SET status = :st,
                    park_reason = :pr,
                    last_error = :err,
                    attempt_count = attempt_count + 1,
                    processed_at = now()
                WHERE id = :iid
                """
            ),
            {
                "iid": str(intent_id),
                "st": status,
                "pr": park_reason,
                "err": last_error[:500] if last_error else None,
            },
        )
    else:
        clear_err = status == "completed"
        await db.execute(
            text(
                """
                UPDATE pujari_tds_accrual_intents
                SET status = :st,
                    park_reason = :pr,
                    processed_at = now(),
                    last_error = CASE WHEN :clear_err THEN NULL ELSE last_error END
                WHERE id = :iid
                """
            ),
            {
                "iid": str(intent_id),
                "st": status,
                "pr": park_reason,
                "clear_err": clear_err,
            },
        )


def _is_duplicate_accrual_error(exc: BaseException) -> bool:
    return "duplicate accrual" in str(exc).lower()


async def reconcile_failed_accrual_intents(
    db: AsyncSession, *, limit: int = 200
) -> dict[str, int]:
    """Auto-reconcile: failed intents whose booking already has a ledger accrual row."""
    rows = (
        await db.execute(
            text(
                """
                SELECT i.id
                FROM pujari_tds_accrual_intents i
                WHERE i.status = 'failed'
                  AND EXISTS (
                      SELECT 1 FROM pujari_tds_facilitation_ledger l
                      WHERE l.booking_id = i.booking_id
                        AND l.entry_type = 'accrual'
                  )
                ORDER BY i.created_at
                LIMIT :lim
                FOR UPDATE OF i
                """
            ),
            {"lim": limit},
        )
    ).scalars().all()

    reconciled = 0
    for intent_id in rows:
        await _mark_intent_status(
            db, intent_id=uuid.UUID(str(intent_id)), status="completed"
        )
        reconciled += 1
    if reconciled:
        log.info("tds_accrual_intents_reconciled", count=reconciled)
    return {"reconciled": reconciled}


async def _run_intent_accrual_with_savepoint(
    db: AsyncSession,
    *,
    intent_id: uuid.UUID,
    booking_id: uuid.UUID,
    pujari_id: uuid.UUID,
    gross_amount: Decimal,
    collected_at: dt.datetime,
    compliance: dict[str, Any],
) -> str:
    """Returns 'processed' or 'failed'. SAVEPOINT isolates DB errors (D6)."""
    try:
        async with db.begin_nested():
            await _execute_accrual(
                db,
                booking_id=booking_id,
                pujari_id=pujari_id,
                gross_amount=gross_amount,
                collected_at=collected_at,
                compliance=compliance,
            )
        # Bookkeeping outside nested scope — survives accrual subtxn rollback on failure.
        await _mark_intent_status(db, intent_id=intent_id, status="completed")
        return "processed"
    except IntegrityError as exc:
        if await lookup_accrual_for_booking(db, booking_id) is not None:
            await _mark_intent_status(db, intent_id=intent_id, status="completed")
            return "processed"
        await _mark_intent_status(
            db,
            intent_id=intent_id,
            status="failed",
            last_error=str(exc),
            increment_attempt=True,
        )
        log.warning(
            "tds_accrual_intent_failed",
            intent_id=str(intent_id),
            booking_id=str(booking_id),
            error=str(exc),
        )
        return "failed"
    except Exception as exc:
        if _is_duplicate_accrual_error(exc) and await lookup_accrual_for_booking(
            db, booking_id
        ) is not None:
            await _mark_intent_status(db, intent_id=intent_id, status="completed")
            return "processed"
        await _mark_intent_status(
            db,
            intent_id=intent_id,
            status="failed",
            last_error=str(exc),
            increment_attempt=True,
        )
        log.warning(
            "tds_accrual_intent_failed",
            intent_id=str(intent_id),
            booking_id=str(booking_id),
            error=str(exc),
        )
        return "failed"


async def process_pending_accrual_intents(
    db: AsyncSession,
    *,
    limit: int = _DEFAULT_PUJARI_BATCH_LIMIT,
    intents_per_pujari_limit: int = _DEFAULT_INTENTS_PER_PUJARI,
) -> dict[str, int]:
    """Ordered per-pujari accrual worker (R4). Returns counts."""
    if not _accrual_enabled():
        return {"processed": 0, "parked": 0, "failed": 0, "reconciled": 0}

    reconcile_stats = await reconcile_failed_accrual_intents(db, limit=limit * 4)

    pujari_ids = (
        await db.execute(
            text(
                """
                SELECT DISTINCT pujari_id
                FROM pujari_tds_accrual_intents
                WHERE status IN ('pending', 'parked')
                ORDER BY pujari_id
                LIMIT :lim
                """
            ),
            {"lim": limit},
        )
    ).scalars().all()

    processed = parked = failed = 0
    for pujari_id in pujari_ids:
        stats = await process_pending_accrual_intents_for_pujari(
            db,
            pujari_id=uuid.UUID(str(pujari_id)),
            intents_limit=intents_per_pujari_limit,
        )
        processed += stats["processed"]
        parked += stats["parked"]
        failed += stats["failed"]
    return {
        "processed": processed,
        "parked": parked,
        "failed": failed,
        "reconciled": reconcile_stats["reconciled"],
    }


async def process_pending_accrual_intents_for_pujari(
    db: AsyncSession,
    *,
    pujari_id: uuid.UUID,
    intents_limit: int = _DEFAULT_INTENTS_PER_PUJARI,
) -> dict[str, int]:
    """Process pending/parked intents for a single pujari (admin safe-fix / worker subset)."""
    if not _accrual_enabled():
        return {"processed": 0, "parked": 0, "failed": 0, "reconciled": 0}

    intents = (
        await db.execute(
            text(
                """
                SELECT id, booking_id, gross_amount, collected_at,
                       snapshot_entity_type, snapshot_pan_on_file, status
                FROM pujari_tds_accrual_intents
                WHERE pujari_id = :pid
                  AND status IN ('pending', 'parked')
                ORDER BY collected_at
                FOR UPDATE
                LIMIT :intent_lim
                """
            ),
            {"pid": str(pujari_id), "intent_lim": intents_limit},
        )
    ).mappings().all()

    processed = parked = failed = 0
    for intent in intents:
        intent_id = uuid.UUID(str(intent["id"]))
        booking_id = uuid.UUID(str(intent["booking_id"]))
        if await lookup_accrual_for_booking(db, booking_id) is not None:
            await _mark_intent_status(db, intent_id=intent_id, status="completed")
            processed += 1
            continue

        from app.services.tds_v3_reversal_service import facilitation_remaining

        rem = await facilitation_remaining(db, booking_id=booking_id)
        snap = await load_booking_tds_v3_snapshot(db, booking_id=booking_id)
        if (
            rem is not None
            and snap.tds_liability_inr > 0
            and rem.tds_liability_inr <= 0
        ):
            await _mark_intent_status(
                db,
                intent_id=intent_id,
                status="cancelled",
                park_reason="facilitation_reversed",
            )
            processed += 1
            continue

        compliance = await _compliance_from_snapshot_or_live(
            db, booking_id=booking_id, pujari_id=pujari_id
        )
        if compliance["entity_type"] is None:
            await _mark_intent_status(
                db,
                intent_id=intent_id,
                status="parked",
                park_reason="entity_type_missing",
            )
            parked += 1
            continue

        outcome = await _run_intent_accrual_with_savepoint(
            db,
            intent_id=intent_id,
            booking_id=booking_id,
            pujari_id=pujari_id,
            gross_amount=Decimal(str(intent["gross_amount"])),
            collected_at=intent["collected_at"],
            compliance=compliance,
        )
        if outcome == "processed":
            processed += 1
        else:
            failed += 1
    return {
        "processed": processed,
        "parked": parked,
        "failed": failed,
        "reconciled": 0,
    }


async def accrue_tds_on_balance_collected(
    db: AsyncSession,
    *,
    booking_id: uuid.UUID,
    pujari_id: uuid.UUID,
    gross_amount: Decimal,
    collected_at: dt.datetime | None = None,
) -> dict[str, Any]:
    """Direct accrual — tests and catch_up only; API uses enqueue_tds_accrual_intent."""
    if not _accrual_enabled():
        return _tds_payload(
            accrual_enabled=False,
            skipped=True,
            message="TDS accrual disabled (launch default).",
        )

    existing = await lookup_accrual_for_booking(db, booking_id)
    if existing is not None:
        cfg = await load_tds_facilitation_config(db)
        fy_row = await _read_fy_row(
            db, pujari_id=pujari_id, fy_start=existing["fy_start"]
        )
        return _tds_payload(
            accrual_enabled=True,
            skipped=False,
            idempotent=True,
            tds_rate=Decimal(existing["tds_rate"]),
            tds_amount=existing["tds_amount"],
            fy_gross_after=fy_row["gross_facilitation"],
            fy_threshold_inr=cfg.individual_fy_threshold_inr,
        )

    compliance = await _compliance_from_snapshot_or_live(
        db, booking_id=booking_id, pujari_id=pujari_id
    )
    if compliance["entity_type"] is None:
        raise HTTPException(
            http.HTTP_422_UNPROCESSABLE_ENTITY,
            "Entity type must be confirmed on your profile before recording balance.",
        )

    when = collected_at or dt.datetime.now(dt.UTC)
    return await _execute_accrual(
        db,
        booking_id=booking_id,
        pujari_id=pujari_id,
        gross_amount=gross_amount,
        collected_at=when,
        compliance=compliance,
    )


async def reverse_tds_if_accrued(
    db: AsyncSession, *, booking_id: uuid.UUID
) -> dict[str, Any]:
    """Lookup assigned pujari and reverse prior accrual if any (R6 wrapper)."""
    return await reverse_tds_on_offline_collection_reversed(db, booking_id=booking_id)


async def reverse_tds_on_offline_collection_reversed(
    db: AsyncSession,
    *,
    booking_id: uuid.UUID,
    pujari_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """R6: reverse when offline collection is reversed — unconditional on flag (R1)."""
    if pujari_id is None:
        row = (
            await db.execute(
                text("SELECT pujari_id FROM bookings WHERE id = :bid FOR UPDATE"),
                {"bid": str(booking_id)},
            )
        ).scalar_one_or_none()
        if row is None:
            return {"reversed": False, "reason": "Booking not found.", "booking_id": str(booking_id)}
        pujari_id = uuid.UUID(str(row))
    else:
        await db.execute(
            text("SELECT id FROM bookings WHERE id = :bid FOR UPDATE"),
            {"bid": str(booking_id)},
        )

    return await reverse_tds_on_cancel(
        db, booking_id=booking_id, pujari_id=pujari_id
    )


async def reverse_tds_on_cancel(
    db: AsyncSession,
    *,
    booking_id: uuid.UUID,
    pujari_id: uuid.UUID,
    refund_reference: str | None = None,
    refund_fraction: Decimal | None = None,
) -> dict[str, Any]:
    """Contra when facilitation is reversed (full legacy cancel or proportional refund)."""
    from app.services.tds_v3_reversal_service import apply_facilitation_reversal

    ref = refund_reference or f"legacy_cancel:{booking_id}"
    frac = refund_fraction if refund_fraction is not None else Decimal("1")
    outcome = await apply_facilitation_reversal(
        db,
        booking_id=booking_id,
        pujari_id=pujari_id,
        refund_reference=ref,
        refund_fraction=frac,
    )
    if outcome.get("reversed"):
        return {
            "reversed": True,
            "booking_id": str(booking_id),
            "tds_amount": outcome.get("tds_reversed_inr"),
            **outcome,
        }
    reason = outcome.get("reason", "Not reversed")
    if outcome.get("idempotent"):
        return {
            "reversed": False,
            "reason": "Already reversed.",
            "booking_id": str(booking_id),
            **outcome,
        }
    if reason in ("Nothing left to reverse", "Cumulative cap — no remainder"):
        return {
            "reversed": False,
            "reason": "Already reversed.",
            "booking_id": str(booking_id),
            **outcome,
        }
    if reason == "No accrual for booking.":
        return outcome
    return {
        "reversed": False,
        "reason": reason,
        "booking_id": str(booking_id),
        **outcome,
    }


async def pujari_fy_tax_summary(
    db: AsyncSession, *, pujari_id: uuid.UUID
) -> dict[str, Any]:
    """Current FY facilitation totals for partner tax-summary screen."""
    now = dt.datetime.now(dt.UTC).astimezone(_tz())
    fy_start = fy_start_for_date(now.date())
    cfg = await load_tds_facilitation_config(db)
    compliance = await _pujari_compliance(db, pujari_id)

    row = (
        await db.execute(
            text(
                """
                SELECT gross_facilitation, tds_accrued
                FROM pujari_tax_year
                WHERE pujari_id = :pid AND fy_start = :fy
                """
            ),
            {"pid": str(pujari_id), "fy": fy_start},
        )
    ).mappings().first()
    tds_accrued = Decimal(str(row["tds_accrued"])) if row else Decimal("0")
    ledger_gross = Decimal(str(row["gross_facilitation"])) if row else Decimal("0")
    from app.services.pujari_fy_pan_gate import current_fy_facilitation_gross, evaluate_fy_pan_gate

    booking_gross = await current_fy_facilitation_gross(
        db, pujari_id=pujari_id, fy_start=fy_start
    )
    fy_gross = max(ledger_gross, booking_gross).quantize(Decimal("0.01"))
    threshold = cfg.individual_fy_threshold_inr
    remaining = max(Decimal("0"), (threshold - fy_gross).quantize(Decimal("0.01")))

    if not compliance["pan_on_file"]:
        message = (
            "Add and verify PAN before FY facilitation crosses ₹5 lakh — above the threshold, "
            "missing PAN triggers 5% fail-safe TDS on the taxable slice (0.1% with operative PAN)."
        )
    elif compliance["entity_type"] in cfg.always_taxed_entity_types:
        message = "Your entity type is subject to TDS on each facilitation collection."
    elif fy_gross >= threshold:
        message = (
            "FY facilitation has crossed ₹5 lakh — TDS applies at 0.1% on the slice above "
            "the threshold (operative PAN)."
        )
    else:
        message = f"₹{remaining} remaining before ₹5L FY TDS threshold."

    from app.services.pujari_fy_pan_gate import evaluate_fy_pan_gate

    gate = evaluate_fy_pan_gate(
        fy_gross_inr=fy_gross,
        pan_on_file=bool(compliance["pan_on_file"]),
        entity_type=compliance["entity_type"],
        cfg=cfg,
    )
    if gate.level in ("warn", "block"):
        message = gate.message

    result = {
        "fy_start": fy_start.isoformat(),
        "fy_gross_facilitation": str(fy_gross.quantize(Decimal("0.01"))),
        "tds_accrued": str(tds_accrued.quantize(Decimal("0.01"))),
        "individual_fy_threshold_inr": str(threshold),
        "threshold_remaining_inr": str(remaining),
        "pan_on_file": bool(compliance["pan_on_file"]),
        "entity_type": compliance["entity_type"],
        "message": message,
    }
    result.update(gate.to_tax_summary_fields())
    return result
