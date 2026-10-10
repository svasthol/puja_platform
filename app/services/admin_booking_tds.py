"""Read-only TDS + collection snapshot for one booking (admin ops)."""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status as http
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.admin_tds_compliance import _intents_table_exists


def _q(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return value.quantize(Decimal("0.01"))


def _build_hints(row: dict[str, Any], intent: dict[str, Any] | None) -> tuple[str, list[str]]:
    hints: list[str] = []
    collected = row["balance_collected_at"] is not None
    snapshot = row["tds_facilitation_fy_applied_at"] is not None
    ledger = bool(row.get("ledger_accrual_present"))

    if not collected:
        hints.append("Offline balance not confirmed in app — no TDS diary line expected yet.")
    if collected and not snapshot:
        hints.append(
            "Collected but accept TDS snapshot missing — accrual may fail; check accept flow."
        )
    if collected and snapshot and not ledger:
        hints.append(
            "Collected with snapshot but no ledger accrual — check TDS accrual backlog or Celery worker."
        )
    if intent and intent.get("status") == "failed":
        err = (intent.get("last_error") or "").lower()
        if "duplicate accrual" in err:
            hints.append(
                "Accrual intent failed: diary line may already exist — mark intent complete or ask engineering."
            )
        else:
            hints.append(f"Accrual intent failed: {(intent.get('last_error') or '')[:200]}")
    if intent and intent.get("status") == "parked":
        hints.append(
            f"Accrual parked ({intent.get('park_reason') or 'unknown'}) — fix partner entity/PAN, then retry."
        )
    if collected and snapshot and ledger:
        hints.append("Collection + snapshot + ledger accrual present — this booking looks healthy for TDS.")

    if intent and intent.get("status") == "failed":
        return "needs_attention", hints
    if collected and not snapshot:
        return "needs_attention", hints
    if collected and snapshot and not ledger and intent:
        return "pending_accrual", hints
    if collected and snapshot and ledger:
        return "ok", hints
    if not collected and snapshot:
        return "accepted_not_collected", hints
    return "in_progress", hints


async def fetch_booking_tds_snapshot(
    db: AsyncSession, *, booking_id: uuid.UUID
) -> dict[str, Any]:
    row = (
        await db.execute(
            text(
                """
                SELECT
                    b.pujari_id,
                    b.balance_collected_at,
                    b.balance_collected_amount,
                    b.tds_facilitation_fy_applied_at,
                    b.tds_liability_inr,
                    b.tds_taxable_base,
                    b.tds_rate_applied,
                    b.tds_collected_online,
                    EXISTS (
                        SELECT 1 FROM pujari_tds_facilitation_ledger l
                        WHERE l.booking_id = b.id AND l.entry_type = 'accrual'
                    ) AS ledger_accrual_present,
                    (
                        SELECT l.fy_start::text
                        FROM pujari_tds_facilitation_ledger l
                        WHERE l.booking_id = b.id AND l.entry_type = 'accrual'
                        LIMIT 1
                    ) AS ledger_fy_start,
                    (
                        SELECT l.gross_amount
                        FROM pujari_tds_facilitation_ledger l
                        WHERE l.booking_id = b.id AND l.entry_type = 'accrual'
                        LIMIT 1
                    ) AS ledger_taxable_base,
                    (
                        SELECT l.tds_amount
                        FROM pujari_tds_facilitation_ledger l
                        WHERE l.booking_id = b.id AND l.entry_type = 'accrual'
                        LIMIT 1
                    ) AS ledger_tds_amount
                FROM bookings b
                WHERE b.id = :bid
                """
            ),
            {"bid": str(booking_id)},
        )
    ).mappings().first()
    if row is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "Booking not found.")

    intent: dict[str, Any] | None = None
    if await _intents_table_exists(db):
        intent = (
            await db.execute(
                text(
                    """
                    SELECT status, park_reason, last_error, attempt_count
                    FROM pujari_tds_accrual_intents
                    WHERE booking_id = :bid
                    """
                ),
                {"bid": str(booking_id)},
            )
        ).mappings().first()
        if intent is not None:
            intent = dict(intent)

    ops_status, hints = _build_hints(dict(row), intent)
    rate = row["tds_rate_applied"]
    return {
        "booking_id": booking_id,
        "pujari_id": uuid.UUID(str(row["pujari_id"])) if row["pujari_id"] else None,
        "accrual_enabled": get_settings().TDS_ACCRUAL_ENABLED,
        "balance_collected_at": str(row["balance_collected_at"])
        if row["balance_collected_at"]
        else None,
        "balance_collected_amount_inr": _q(
            Decimal(str(row["balance_collected_amount"]))
            if row["balance_collected_amount"] is not None
            else None
        ),
        "accept_tds_snapshot_at": str(row["tds_facilitation_fy_applied_at"])
        if row["tds_facilitation_fy_applied_at"]
        else None,
        "tds_liability_inr": _q(
            Decimal(str(row["tds_liability_inr"])) if row["tds_liability_inr"] is not None else None
        ),
        "tds_taxable_base_inr": _q(
            Decimal(str(row["tds_taxable_base"])) if row["tds_taxable_base"] is not None else None
        ),
        "tds_rate_applied": str(rate) if rate is not None else None,
        "tds_collected_online_inr": _q(
            Decimal(str(row["tds_collected_online"]))
            if row["tds_collected_online"] is not None
            else None
        ),
        "ledger_accrual_present": bool(row["ledger_accrual_present"]),
        "ledger_fy_start": row["ledger_fy_start"],
        "ledger_taxable_base_inr": _q(
            Decimal(str(row["ledger_taxable_base"]))
            if row["ledger_taxable_base"] is not None
            else None
        ),
        "ledger_tds_amount_inr": _q(
            Decimal(str(row["ledger_tds_amount"]))
            if row["ledger_tds_amount"] is not None
            else None
        ),
        "accrual_intent_status": intent["status"] if intent else None,
        "accrual_intent_park_reason": intent.get("park_reason") if intent else None,
        "accrual_intent_last_error": intent.get("last_error") if intent else None,
        "accrual_intent_attempt_count": int(intent["attempt_count"])
        if intent and intent.get("attempt_count") is not None
        else None,
        "ops_status": ops_status,
        "hints": hints,
    }
