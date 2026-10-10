"""
TEST ONLY — Sprint 2 TDS & compliance helpers for E2E UI (no app imports).
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

E2E_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = E2E_ROOT.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.e2e.sprint2_tds_model import (  # noqa: E402
    TdsLedgerState,
    accrue_tds_on_balance_collected,
    load_tds_config,
    pan_accept_gate,
    reverse_tds_on_cancel,
    tds_calculator_preview,
)
from app.services.pricing import fy_turnover_monitor  # noqa: E402

# Module-level simulator for POST accrual/reversal demos (no DB writes).
_demo_state = TdsLedgerState()


def reset_demo_state() -> None:
    global _demo_state
    _demo_state = TdsLedgerState()


def current_tds_config() -> Any:
    try:
        from test_db import fetch_tds_facilitation_settings

        return load_tds_config(fetch_tds_facilitation_settings())
    except Exception:
        return load_tds_config(None)


def tds_preview(
    *,
    entity_type: str | None,
    pan_on_file: bool,
    fy_gross_before: Decimal,
    transaction_amount: Decimal,
    config=None,
) -> dict[str, Any]:
    cfg = config or current_tds_config()
    return tds_calculator_preview(
        entity_type=entity_type,
        pan_on_file=pan_on_file,
        fy_gross_before=fy_gross_before,
        transaction_amount=transaction_amount,
        config=cfg,
    )


def simulate_accrual(
    *,
    booking_id: str,
    pujari_id: str,
    entity_type: str | None,
    pan_on_file: bool,
    gross_amount: Decimal,
    tds_accrual_enabled: bool = True,
    reset: bool = False,
) -> dict[str, Any]:
    global _demo_state
    if reset:
        reset_demo_state()
    result = accrue_tds_on_balance_collected(
        _demo_state,
        booking_id=booking_id,
        pujari_id=pujari_id,
        entity_type=entity_type,
        pan_on_file=pan_on_file,
        gross_amount=gross_amount,
        tds_accrual_enabled=tds_accrual_enabled,
        config=current_tds_config(),
    )
    result["ledger_snapshot"] = {
        "entries": list(_demo_state.entries),
        "fy_gross": str(_demo_state.fy_gross),
        "tds_accrued": str(_demo_state.tds_accrued),
    }
    return result


def simulate_reversal(
    *,
    booking_id: str,
    pujari_id: str,
) -> dict[str, Any]:
    result = reverse_tds_on_cancel(
        _demo_state, booking_id=booking_id, pujari_id=pujari_id
    )
    result["ledger_snapshot"] = {
        "entries": list(_demo_state.entries),
        "fy_gross": str(_demo_state.fy_gross),
        "tds_accrued": str(_demo_state.tds_accrued),
    }
    return result


def turnover_preview(fy_fee_revenue: Decimal, config=None) -> dict[str, Any]:
    cfg = config or current_tds_config()
    return fy_turnover_monitor(fy_fee_revenue, config=cfg)


def pan_gate_preview(
    *,
    pan_on_file: bool,
    gate_enabled: bool,
) -> dict[str, Any]:
    return pan_accept_gate(pan_on_file=pan_on_file, gate_enabled=gate_enabled)


def booking_tds_settlement_view(row: dict[str, Any]) -> dict[str, Any]:
    """TDS settlement preview for one booking row from test_db (read-only)."""
    from test_db import fetch_pujari_compliance, fetch_fy_booking_fee_revenue

    total = Decimal(str(row.get("total_amount") or "0"))
    balance_collected = bool(row.get("balance_collected_at"))
    bal_amt = row.get("balance_collected_amount")
    gross = (
        Decimal(str(bal_amt))
        if bal_amt is not None
        else (total if balance_collected else Decimal("0"))
    )

    pujari_id = row.get("pujari_id")
    compliance = None
    tds_preview_result = None
    accrual_would_run = None

    if pujari_id:
        compliance = fetch_pujari_compliance(str(pujari_id))
        entity_type = compliance.get("entity_type")
        pan_on_file = bool(compliance.get("pan_on_file"))
        fy_gross = Decimal(str(compliance.get("fy_gross_facilitation") or "0"))
        if gross > 0:
            tds_preview_result = tds_preview(
                entity_type=entity_type,
                pan_on_file=pan_on_file,
                fy_gross_before=fy_gross,
                transaction_amount=gross,
            )
        if balance_collected and gross > 0:
            accrual_would_run = {
                "trigger": "confirm-balance-collected",
                "tds_accrual_enabled_in_production": False,
                "would_write_ledger": entity_type is not None and tds_preview_result
                and tds_preview_result.get("ok"),
                "preview": tds_preview_result,
            }

    cfg = current_tds_config()
    fy_revenue = fetch_fy_booking_fee_revenue()
    turnover = turnover_preview(Decimal(str(fy_revenue)), config=cfg)

    return {
        "tds_config": cfg.to_json(),
        "booking_id": row.get("booking_id"),
        "implementation": "preview",
        "note": (
            "Sprint 2 TDS accrual is stubbed in production (TDS_ACCRUAL_ENABLED=false). "
            "This view simulates what will happen at confirm-balance-collected."
        ),
        "current": {
            "status": row.get("status"),
            "total_amount": row.get("total_amount"),
            "balance_collected_at": row.get("balance_collected_at"),
            "balance_collected_amount": row.get("balance_collected_amount"),
            "pujari_id": pujari_id,
        },
        "pujari_compliance": compliance,
        "tds_preview": tds_preview_result,
        "accrual_at_balance_collected": accrual_would_run,
        "fy_turnover": turnover,
        "pan_gate": pan_gate_preview(
            pan_on_file=bool(compliance and compliance.get("pan_on_file")),
            gate_enabled=False,
        ),
    }
