"""TDS v3 facilitation math — unit tests (SSOT: TDS_V3_IMPLEMENTATION.md)."""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.pricing import parse_tds_facilitation_config, tds_on_facilitation
from app.services.pricing_tds_v3 import (
    charge_breakdown,
    compute_facilitation_accrual,
    deposit_round_inr,
    reverse_facilitation,
    taxable_facilitation_base,
)


def test_no_pan_under_five_lakh_zero_tds():
    rate, tds = tds_on_facilitation(
        entity_type="individual",
        pan_on_file=False,
        fy_gross_before=Decimal("100000"),
        this_amount=Decimal("2100"),
    )
    assert rate == Decimal("0")
    assert tds == Decimal("0")


def test_crossing_excess_slice_operative_pan():
    """FY 4.9L + 20k → taxable 10k @ 0.1% = ₹10."""
    result = compute_facilitation_accrual(
        entity_type="individual",
        pan_on_file=True,
        pan_status="operative",
        fy_gross_before=Decimal("490000"),
        this_amount=Decimal("20000"),
    )
    assert result.rate == Decimal("0.001")
    assert result.taxable_base == Decimal("10000.00")
    assert result.tds_amount == Decimal("10.00")
    assert result.turnover_increment == Decimal("20000.00")
    assert result.fy_gross_after == Decimal("510000.00")
    assert result.deduction_latched_after is True


def test_after_latch_full_amount_taxed():
    result = compute_facilitation_accrual(
        entity_type="individual",
        pan_on_file=True,
        pan_status="operative",
        fy_gross_before=Decimal("510000"),
        this_amount=Decimal("5000"),
        deduction_latched=True,
    )
    assert result.taxable_base == Decimal("5000.00")
    assert result.tds_amount == Decimal("5.00")


def test_no_pan_above_threshold_fail_safe_rate():
    """Gate-off math: 5% applies only above ₹5L (not normal product path)."""
    rate, tds = tds_on_facilitation(
        entity_type="individual",
        pan_on_file=False,
        fy_gross_before=Decimal("500000"),
        this_amount=Decimal("10000"),
        deduction_latched=True,
    )
    assert rate == Decimal("0.05")
    assert tds == Decimal("500.00")


def test_firm_always_taxed_from_rupee_one():
    rate, tds = tds_on_facilitation(
        entity_type="firm",
        pan_on_file=True,
        pan_status="operative",
        fy_gross_before=Decimal("0"),
        this_amount=Decimal("2100"),
    )
    assert rate == Decimal("0.001")
    assert tds == Decimal("2.10")


def test_taxable_base_excess_vs_full_config():
    cfg = parse_tds_facilitation_config({"tds_crossing_base": "full"})
    base = taxable_facilitation_base(
        entity_type="individual",
        fy_gross_before=Decimal("490000"),
        this_amount=Decimal("20000"),
        deduction_latched=False,
        config=cfg,
    )
    assert base == Decimal("20000.00")


def test_charge_breakdown_t6():
    br = charge_breakdown(
        total_amount=Decimal("21000"),
        booking_fee=Decimal("61"),
        tds_amount=Decimal("10"),
        tds_rate=Decimal("0.001"),
    )
    assert br.razorpay_online_inr == Decimal("71.00")
    assert br.amount_due_offline_inr == Decimal("20990.00")
    assert br.tds_collected_online_inr == Decimal("10.00")


def test_charge_breakdown_rejects_tds_over_total():
    with pytest.raises(ValueError, match="tds_amount"):
        charge_breakdown(
            total_amount=Decimal("100"),
            booking_fee=Decimal("61"),
            tds_amount=Decimal("101"),
            tds_rate=Decimal("0.05"),
        )


def test_reverse_facilitation_proportional():
    rev = reverse_facilitation(
        booking_turnover=Decimal("20000"),
        ledger_taxable_base=Decimal("10000"),
        ledger_tds_amount=Decimal("10"),
        refund_fraction=Decimal("0.5"),
    )
    assert rev.turnover_reversal == Decimal("10000.00")
    assert rev.taxable_base_reversal == Decimal("5000.00")
    assert rev.tds_reversal == Decimal("5.00")


def test_deposit_round_nearest_ten():
    assert deposit_round_inr(Decimal("1004.99")) == Decimal("1000")
    assert deposit_round_inr(Decimal("1005.00")) == Decimal("1010")


def test_custom_threshold_respects_excess_slice():
    cfg = parse_tds_facilitation_config({"individual_fy_threshold_inr": 400000})
    rate, tds = tds_on_facilitation(
        entity_type="individual",
        pan_on_file=True,
        pan_status="operative",
        fy_gross_before=Decimal("390000"),
        this_amount=Decimal("20000"),
        config=cfg,
    )
    assert rate == Decimal("0.001")
    assert tds == Decimal("10.00")
