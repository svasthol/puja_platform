"""
Sprint 2 launch-gate contract tests (TEST ONLY — no app/ imports).

TDS accrual, PAN gate, FY turnover monitor before production wiring.
Run: pytest tests/e2e/test_sprint2_tds_launch_e2e.py -q
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from tests.e2e.sprint2_tds_model import (
    FY_TURNOVER_BLOCK_INR,
    FY_TURNOVER_WARN_INR,
    TdsLedgerState,
    accrue_tds_on_balance_collected,
    fy_turnover_monitor,
    pan_accept_gate,
    reverse_tds_on_cancel,
    tds_on_facilitation,
)

PUJA_GROSS = Decimal("2100.00")
BOOKING_ID = "b0000000-0000-4000-8000-000000000001"
PUJARI_ID = "p0000000-0000-4000-8000-000000000001"


def test_tds_accrual_at_balance_collection_crossing_five_lakh():
    """#15 — TDS accrues at confirm-balance-collected when FY crosses ₹5L."""
    crossing_gross = Decimal("20000")
    state = TdsLedgerState(fy_gross=Decimal("490000"))
    result = accrue_tds_on_balance_collected(
        state,
        booking_id=BOOKING_ID,
        pujari_id=PUJARI_ID,
        entity_type="individual",
        pan_on_file=True,
        gross_amount=crossing_gross,
    )
    assert result["accrual_enabled"] is True
    assert result["idempotent"] is False
    entry = result["ledger_entry"]
    assert entry["entry_type"] == "accrual"
    assert entry["tds_rate"] == "0.001"
    assert entry["tds_amount"] == "10.00"
    assert entry["gross_amount"] == "10000.00"
    assert result["fy_gross_after"] == "510000.00"
    assert result["tds_accrued_total"] == "10.00"


def test_tds_accrual_no_pan_zero_under_five_lakh():
    """#16 v3 — No PAN still ₹0 TDS until FY crosses ₹5L."""
    state = TdsLedgerState()
    result = accrue_tds_on_balance_collected(
        state,
        booking_id=BOOKING_ID,
        pujari_id=PUJARI_ID,
        entity_type="individual",
        pan_on_file=False,
        gross_amount=PUJA_GROSS,
    )
    entry = result["ledger_entry"]
    assert entry["tds_rate"] == "0"
    assert entry["tds_amount"] == "0.00"


def test_tds_accrual_firm_always_point_one_percent():
    """Firm with PAN — 0.1% regardless of FY threshold."""
    state = TdsLedgerState()
    rate, tds = tds_on_facilitation(
        entity_type="firm",
        pan_on_file=True,
        fy_gross_before=Decimal("0"),
        this_amount=PUJA_GROSS,
    )
    assert rate == Decimal("0.001")
    assert tds == Decimal("2.10")


def test_tds_accrual_idempotent_per_booking():
    """One accrual per booking — duplicate confirm-balance-collected is no-op."""
    state = TdsLedgerState(fy_gross=Decimal("490000"))
    first = accrue_tds_on_balance_collected(
        state,
        booking_id=BOOKING_ID,
        pujari_id=PUJARI_ID,
        entity_type="individual",
        pan_on_file=True,
        gross_amount=PUJA_GROSS,
    )
    second = accrue_tds_on_balance_collected(
        state,
        booking_id=BOOKING_ID,
        pujari_id=PUJARI_ID,
        entity_type="individual",
        pan_on_file=True,
        gross_amount=PUJA_GROSS,
    )
    assert first["idempotent"] is False
    assert second["idempotent"] is True
    assert len(state.entries) == 1
    assert state.fy_gross == Decimal("492100.00")


def test_tds_accrual_stubbed_when_flag_off():
    """Launch stub — TDS_ACCRUAL_ENABLED=false skips ledger writes."""
    state = TdsLedgerState()
    result = accrue_tds_on_balance_collected(
        state,
        booking_id=BOOKING_ID,
        pujari_id=PUJARI_ID,
        entity_type="individual",
        pan_on_file=True,
        gross_amount=PUJA_GROSS,
        tds_accrual_enabled=False,
    )
    assert result["skipped"] is True
    assert len(state.entries) == 0


def test_tds_reversal_on_cancel_after_accrual():
    """Reversal entry restores FY turnover and TDS accrued totals."""
    state = TdsLedgerState(fy_gross=Decimal("490000"))
    accrue_tds_on_balance_collected(
        state,
        booking_id=BOOKING_ID,
        pujari_id=PUJARI_ID,
        entity_type="individual",
        pan_on_file=True,
        gross_amount=Decimal("20000"),
    )
    rev = reverse_tds_on_cancel(
        state, booking_id=BOOKING_ID, pujari_id=PUJARI_ID
    )
    assert rev["reversed"] is True
    assert rev["ledger_entry"]["entry_type"] == "reversal"
    assert state.fy_gross == Decimal("490000.00")
    assert state.tds_accrued == Decimal("0.00")
    assert len(state.entries) == 2


def test_fy_turnover_warn_at_eighteen_lakh():
    """#17 — G2 monitor warns at ₹18L platform fee revenue."""
    result = fy_turnover_monitor(FY_TURNOVER_WARN_INR)
    assert result["level"] == "warn"
    assert "GST registration" in result["message"]


def test_fy_turnover_block_at_twenty_lakh():
    """#17 — G2 monitor escalates at ₹20L."""
    result = fy_turnover_monitor(FY_TURNOVER_BLOCK_INR)
    assert result["level"] == "block"


def test_fy_turnover_ok_below_warn():
    """#17 — Safe runway below ₹18L."""
    result = fy_turnover_monitor(Decimal("500000"))
    assert result["level"] == "ok"


def test_pan_accept_gate_blocks_without_pan():
    """PAN gate — accept offer blocked when PAN missing."""
    result = pan_accept_gate(pan_on_file=False, gate_enabled=True)
    assert result["allowed"] is False
    assert result["http_status"] == 422


def test_pan_accept_gate_allows_with_pan():
    """PAN gate — accept allowed when PAN on file."""
    result = pan_accept_gate(pan_on_file=True, gate_enabled=True)
    assert result["allowed"] is True


def test_pan_accept_gate_disabled_at_launch():
    """Launch default — gate off, accept always allowed."""
    result = pan_accept_gate(pan_on_file=False, gate_enabled=False)
    assert result["allowed"] is True
    assert result["gate_enabled"] is False


def test_tds_null_entity_type_raises():
    """#18 — NULL entity_type must not silently hit nil band."""
    with pytest.raises(ValueError, match="entity_type required"):
        tds_on_facilitation(
            entity_type=None,
            pan_on_file=True,
            fy_gross_before=Decimal("490000"),
            this_amount=Decimal("20000"),
        )


def test_tds_invalid_entity_type_raises():
    """Invalid entity_type rejected before accrual."""
    with pytest.raises(ValueError, match="entity_type required"):
        tds_on_facilitation(
            entity_type="partnership",
            pan_on_file=True,
            fy_gross_before=Decimal("0"),
            this_amount=PUJA_GROSS,
        )


def test_individual_below_threshold_zero_tds():
    """Individual/HUF with PAN — 0% until FY crosses ₹5L."""
    rate, tds = tds_on_facilitation(
        entity_type="individual",
        pan_on_file=True,
        fy_gross_before=Decimal("100000"),
        this_amount=PUJA_GROSS,
    )
    assert rate == Decimal("0")
    assert tds == Decimal("0")


def test_tds_uses_dynamic_config_threshold():
    """Admin-tunable ₹5L threshold — custom config changes accrual outcome."""
    from app.services.pricing import TdsFacilitationConfig, tds_on_facilitation

    custom = TdsFacilitationConfig(
        no_pan_rate_pct=Decimal("5"),
        pan_entity_rate_pct=Decimal("0.1"),
        individual_fy_threshold_inr=Decimal("400000"),
        individual_fy_pan_warn_inr=Decimal("360000"),
        fy_turnover_warn_inr=Decimal("1800000"),
        fy_turnover_block_inr=Decimal("2000000"),
        always_taxed_entity_types=frozenset({"firm", "trust", "company", "aop", "other"}),
        tds_crossing_base="excess_slice",
    )
    rate, tds = tds_on_facilitation(
        entity_type="individual",
        pan_on_file=True,
        fy_gross_before=Decimal("390000"),
        this_amount=Decimal("20000"),
        config=custom,
        pan_status="operative",
    )
    assert rate == Decimal("0.001")
    assert tds == Decimal("10.00")


def test_e2e_ui_tds_preview_aligns_with_model():
    """E2E UI compliance module must use same contract math."""
    from tests.e2e_ui.sprint2_compliance import tds_preview

    preview = tds_preview(
        entity_type="individual",
        pan_on_file=True,
        fy_gross_before=Decimal("490000"),
        transaction_amount=Decimal("20000"),
    )
    assert preview["ok"] is True
    assert preview["tds_amount_inr"] == "10.00"
