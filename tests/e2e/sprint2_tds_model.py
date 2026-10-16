"""
TEST ONLY — Sprint 2 TDS contract model aligned with app/services/pricing.py.

TDS slabs load from platform_settings.tds_facilitation when available.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.services.pricing_tds_v3 import compute_facilitation_accrual
from app.services.pricing import (
    ALLOWED_ENTITY_TYPES,
    TdsFacilitationConfig,
    default_tds_facilitation_config,
    fy_turnover_monitor,
    parse_tds_facilitation_config,
    tds_on_facilitation,
)

# Back-compat constants (defaults — use load_tds_config() for live values).
_DEFAULT = default_tds_facilitation_config()
FY_TURNOVER_WARN_INR = _DEFAULT.fy_turnover_warn_inr
FY_TURNOVER_BLOCK_INR = _DEFAULT.fy_turnover_block_inr
INDIVIDUAL_TDS_THRESHOLD_INR = _DEFAULT.individual_fy_threshold_inr
NO_PAN_TDS_RATE = _DEFAULT.no_pan_rate
PAN_ENTITY_TDS_RATE = _DEFAULT.pan_entity_rate


def load_tds_config(value_json: dict | None = None) -> TdsFacilitationConfig:
    return parse_tds_facilitation_config(value_json)


def pan_accept_gate(
    *,
    pan_on_file: bool,
    gate_enabled: bool = True,
) -> dict[str, Any]:
    """Simulate accept-offer gate when PAN_ACCEPT_GATE_ENABLED=true."""
    if not gate_enabled:
        return {
            "gate_enabled": False,
            "allowed": True,
            "http_status": None,
            "detail": "PAN gate disabled (launch default).",
        }
    if pan_on_file:
        return {
            "gate_enabled": True,
            "allowed": True,
            "http_status": None,
            "detail": "PAN on file — accept allowed.",
        }
    return {
        "gate_enabled": True,
        "allowed": False,
        "http_status": 422,
        "detail": "PAN must be on file before accepting bookings.",
    }


@dataclass
class TdsLedgerState:
    """In-memory ledger simulator for E2E contract tests."""

    fy_gross: Decimal = Decimal("0")
    tds_accrued: Decimal = Decimal("0")
    deduction_latched: bool = False
    entries: list[dict[str, Any]] = field(default_factory=list)
    accrual_booking_ids: set[str] = field(default_factory=set)


def accrue_tds_on_balance_collected(
    state: TdsLedgerState,
    *,
    booking_id: str,
    pujari_id: str,
    entity_type: str | None,
    pan_on_file: bool,
    gross_amount: Decimal,
    fy_start: str = "2026-04-01",
    tds_accrual_enabled: bool = True,
    config: TdsFacilitationConfig | None = None,
) -> dict[str, Any]:
    """Simulate POST confirm-balance-collected TDS accrual (Sprint 2)."""
    gross = gross_amount.quantize(Decimal("0.01"))
    if not tds_accrual_enabled:
        return {
            "accrual_enabled": False,
            "skipped": True,
            "reason": "TDS_ACCRUAL_ENABLED=false (launch stub).",
            "booking_id": booking_id,
        }
    if booking_id in state.accrual_booking_ids:
        existing = next(
            e for e in state.entries if e["booking_id"] == booking_id and e["entry_type"] == "accrual"
        )
        return {
            "accrual_enabled": True,
            "idempotent": True,
            "ledger_entry": existing,
            "fy_gross_after": str(state.fy_gross),
            "tds_accrued_total": str(state.tds_accrued),
        }

    accrual = compute_facilitation_accrual(
        entity_type=entity_type,
        pan_on_file=pan_on_file,
        fy_gross_before=state.fy_gross,
        this_amount=gross,
        deduction_latched=state.deduction_latched,
        config=config,
    )
    entry = {
        "entry_type": "accrual",
        "booking_id": booking_id,
        "pujari_id": pujari_id,
        "booking_turnover": str(gross),
        "gross_amount": str(accrual.taxable_base),
        "tds_rate": format(accrual.rate.normalize(), "f"),
        "tds_amount": str(accrual.tds_amount),
        "fy_start": fy_start,
        "fy_gross_before": str(state.fy_gross),
    }
    state.fy_gross = accrual.fy_gross_after
    state.tds_accrued = (state.tds_accrued + accrual.tds_amount).quantize(Decimal("0.01"))
    state.deduction_latched = accrual.deduction_latched_after
    state.entries.append(entry)
    state.accrual_booking_ids.add(booking_id)
    return {
        "accrual_enabled": True,
        "idempotent": False,
        "ledger_entry": entry,
        "fy_gross_after": str(state.fy_gross),
        "tds_accrued_total": str(state.tds_accrued),
    }


def reverse_tds_on_cancel(
    state: TdsLedgerState,
    *,
    booking_id: str,
    pujari_id: str,
    fy_start: str = "2026-04-01",
) -> dict[str, Any]:
    """Simulate reversal ledger entry when booking cancelled after accrual."""
    accrual = next(
        (
            e
            for e in state.entries
            if e["booking_id"] == booking_id and e["entry_type"] == "accrual"
        ),
        None,
    )
    if accrual is None:
        return {
            "reversed": False,
            "reason": "No accrual found for booking.",
            "booking_id": booking_id,
        }
    turnover = Decimal(accrual["booking_turnover"])
    taxable = Decimal(accrual["gross_amount"])
    tds_amount = Decimal(accrual["tds_amount"])
    entry = {
        "entry_type": "reversal",
        "booking_id": booking_id,
        "pujari_id": pujari_id,
        "booking_turnover": str(turnover),
        "gross_amount": str(taxable),
        "tds_amount": str(tds_amount),
        "fy_start": fy_start,
        "reverses_accrual": accrual,
    }
    state.fy_gross = max(Decimal("0"), (state.fy_gross - turnover).quantize(Decimal("0.01")))
    state.tds_accrued = max(Decimal("0"), (state.tds_accrued - tds_amount).quantize(Decimal("0.01")))
    state.entries.append(entry)
    state.accrual_booking_ids.discard(booking_id)
    return {
        "reversed": True,
        "ledger_entry": entry,
        "fy_gross_after": str(state.fy_gross),
        "tds_accrued_total": str(state.tds_accrued),
    }


def tds_calculator_preview(
    *,
    entity_type: str | None,
    pan_on_file: bool,
    fy_gross_before: Decimal,
    transaction_amount: Decimal,
    config: TdsFacilitationConfig | None = None,
) -> dict[str, Any]:
    """UI/API helper — TDS rate preview without mutating ledger."""
    cfg = config or default_tds_facilitation_config()
    try:
        rate, tds = tds_on_facilitation(
            entity_type=entity_type,
            pan_on_file=pan_on_file,
            fy_gross_before=fy_gross_before,
            this_amount=transaction_amount,
            config=cfg,
        )
        return {
            "ok": True,
            "entity_type": entity_type,
            "pan_on_file": pan_on_file,
            "fy_gross_before_inr": str(fy_gross_before.quantize(Decimal("0.01"))),
            "transaction_amount_inr": str(transaction_amount.quantize(Decimal("0.01"))),
            "tds_rate": format(rate.normalize(), "f"),
            "tds_amount_inr": str(tds),
            "fy_gross_after_inr": str(
                (fy_gross_before + transaction_amount).quantize(Decimal("0.01"))
            ),
            "config": cfg.to_json(),
        }
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
