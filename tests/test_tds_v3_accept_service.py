"""TDS v3 accept-time acceptance math (T6 spec cases)."""
from __future__ import annotations

from decimal import Decimal

from app.services.pricing_tds_v3 import charge_breakdown, compute_facilitation_accrual


def test_below_five_lakh_fee_only_offline_full():
    r = compute_facilitation_accrual(
        entity_type="individual",
        pan_on_file=True,
        pan_status="operative",
        fy_gross_before=Decimal("100000"),
        this_amount=Decimal("5000"),
    )
    assert r.tds_amount == Decimal("0")
    br = charge_breakdown(
        total_amount=Decimal("5000"),
        booking_fee=Decimal("61"),
        tds_amount=Decimal("0"),
        tds_rate=Decimal("0"),
    )
    assert br.razorpay_online_inr == Decimal("61.00")
    assert br.amount_due_offline_inr == Decimal("5000.00")


def test_post_crossing_three_thousand_operative_pan():
    r = compute_facilitation_accrual(
        entity_type="individual",
        pan_on_file=True,
        pan_status="operative",
        fy_gross_before=Decimal("510000"),
        this_amount=Decimal("3000"),
        deduction_latched=True,
    )
    assert r.taxable_base == Decimal("3000.00")
    assert r.tds_amount == Decimal("3.00")
    br = charge_breakdown(
        total_amount=Decimal("3000"),
        booking_fee=Decimal("61"),
        tds_amount=r.tds_amount,
        tds_rate=r.rate,
    )
    assert br.tds_collected_online_inr == Decimal("3.00")
    assert br.amount_due_offline_inr == Decimal("2997.00")


def test_crossing_booking_excess_slice():
    r = compute_facilitation_accrual(
        entity_type="individual",
        pan_on_file=True,
        pan_status="operative",
        fy_gross_before=Decimal("495000"),
        this_amount=Decimal("15000"),
    )
    assert r.taxable_base == Decimal("10000.00")
    assert r.tds_amount == Decimal("10.00")
    br = charge_breakdown(
        total_amount=Decimal("15000"),
        booking_fee=Decimal("61"),
        tds_amount=r.tds_amount,
        tds_rate=r.rate,
    )
    assert br.amount_due_offline_inr == Decimal("14990.00")
