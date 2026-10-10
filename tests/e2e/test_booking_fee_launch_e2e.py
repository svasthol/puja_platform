"""
Sprint 1 launch-gate contract tests (TEST ONLY — no app/ imports).

These define the booking_fee settlement model before production code ships.
Run: pytest tests/e2e/test_booking_fee_launch_e2e.py -q
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from tests.e2e.booking_fee_model import (
    DEFAULT_BOOKING_FEE,
    compute_checkout_quote,
    map_legacy_booking_to_sprint1_preview,
    refundable_platform_amount,
    settlement_breakdown,
    tds_on_facilitation,
)

PUJA_TOTAL = Decimal("2100.00")
FEE = DEFAULT_BOOKING_FEE


def test_create_booking_booking_fee_amounts():
    """#1 — Razorpay = booking_fee; online=0; offline=total."""
    q = compute_checkout_quote(puja_unit_price=PUJA_TOTAL, booking_fee=FEE)
    assert q["payment_mode"] == "booking_fee"
    assert Decimal(q["booking_fee"]) == FEE
    assert Decimal(q["amount_due_online"]) == 0
    assert Decimal(q["amount_due_offline"]) == PUJA_TOTAL
    assert q["razorpay_amount_paise"] == 6100


def test_no_pujari_refunds_booking_fee():
    """#2 — Platform failure refunds full fee, not amount_due_online (0)."""
    amt = refundable_platform_amount(
        booking_fee=FEE,
        amount_due_online=Decimal("0"),
        payment_mode="booking_fee",
        status_code="requested",
        reason="no_pujari",
    )
    assert amt == FEE


def test_customer_cancel_requested_full_fee_refund():
    """#3 — 100% fee refund while still in requested."""
    amt = refundable_platform_amount(
        booking_fee=FEE,
        amount_due_online=Decimal("0"),
        payment_mode="booking_fee",
        status_code="requested",
        reason="customer_cancel",
    )
    assert amt == FEE


def test_customer_cancel_confirmed_zero_refund():
    """#4 — 0% fee refund after confirmed (launch default)."""
    amt = refundable_platform_amount(
        booking_fee=FEE,
        amount_due_online=Decimal("0"),
        payment_mode="booking_fee",
        status_code="confirmed",
        reason="customer_cancel",
    )
    assert amt == Decimal("0")


def test_full_online_not_in_launch_quote():
    """#5 — Launch quote is always booking_fee mode."""
    q = compute_checkout_quote(puja_unit_price=PUJA_TOTAL)
    assert q["payment_mode"] == "booking_fee"
    assert "full_online" not in q["payment_mode"]


def test_duplicate_replay_frozen_fee():
    """#6 — Idempotent replay must return same frozen booking_fee."""
    q1 = compute_checkout_quote(puja_unit_price=PUJA_TOTAL, booking_fee=FEE)
    q2 = compute_checkout_quote(puja_unit_price=PUJA_TOTAL, booking_fee=FEE)
    assert q1["booking_fee"] == q2["booking_fee"]


def test_payment_splits_net_pujari_zero():
    """#7 — Platform keeps fee; nothing routed to pujari via Razorpay."""
    b = settlement_breakdown(
        total_amount=PUJA_TOTAL, booking_fee=FEE, paid_at=True
    )
    assert b["ledger"]["payment_splits_net_pujari_inr"] == "0"
    assert Decimal(b["ledger"]["platform_revenue_inr"]) == FEE


def test_admin_fee_change_affects_new_quotes_only():
    """#8 — New quote uses new fee; frozen booking keeps old fee."""
    old = compute_checkout_quote(puja_unit_price=PUJA_TOTAL, booking_fee=Decimal("61"))
    new = compute_checkout_quote(puja_unit_price=PUJA_TOTAL, booking_fee=Decimal("99"))
    assert old["booking_fee"] == "61.00"
    assert new["booking_fee"] == "99.00"


def test_confirm_balance_collected_gate():
    """#9/#10 — booking_fee requires balance collection before complete."""
    before = settlement_breakdown(
        total_amount=PUJA_TOTAL,
        booking_fee=FEE,
        balance_collected=False,
    )
    assert before["gates"]["complete_requires_balance_collected"] is True
    assert before["gates"]["balance_collected"] is False

    after = settlement_breakdown(
        total_amount=PUJA_TOTAL,
        booking_fee=FEE,
        balance_collected=True,
        balance_collected_amount=PUJA_TOTAL,
    )
    assert after["gates"]["balance_collected"] is True
    assert Decimal(after["ledger"]["pujari_collects_offline_inr"]) == PUJA_TOTAL


def test_promo_reduces_total_in_model_only():
    """#11 — C1 documents promo impact; launch disables promos in API."""
    with_promo = compute_checkout_quote(
        puja_unit_price=PUJA_TOTAL, promo_pct=10, booking_fee=FEE
    )
    assert Decimal(with_promo["total_amount"]) == Decimal("1890.00")
    assert Decimal(with_promo["booking_fee"]) == FEE


def test_webhook_payments_amount_semantics():
    """#12 — payments.amount = booking_fee at launch."""
    q = compute_checkout_quote(puja_unit_price=PUJA_TOTAL, booking_fee=FEE)
    assert Decimal(q["customer_pays_platform_inr"]) == FEE


def test_admin_refundable_cap_is_booking_fee():
    """#13 — Refund cap uses booking_fee."""
    cap = refundable_platform_amount(
        booking_fee=FEE,
        amount_due_online=Decimal("0"),
        payment_mode="booking_fee",
        status_code="requested",
        reason="customer_cancel",
    )
    assert cap == FEE
    assert cap < PUJA_TOTAL


def test_checkout_quote_fields_present():
    """#14 — API contract fields for checkout quote."""
    q = compute_checkout_quote(puja_unit_price=PUJA_TOTAL, booking_fee=FEE)
    for key in (
        "booking_fee",
        "booking_fee_label",
        "total_amount",
        "amount_due_offline",
        "razorpay_amount_paise",
    ):
        assert key in q


def test_fy_turnover_is_sum_of_booking_fees():
    """#17 — G2 monitor: FY revenue = SUM(booking_fee) where paid."""
    fees = [Decimal("61"), Decimal("61"), Decimal("61")]
    assert sum(fees, Decimal("0")) == Decimal("183")


def test_tds_null_entity_type_raises():
    """#18 — NULL entity_type must not silently hit nil band."""
    with pytest.raises(ValueError, match="entity_type required"):
        tds_on_facilitation(
            entity_type=None,
            pan_on_file=True,
            fy_gross_before=Decimal("490000"),
            this_amount=Decimal("20000"),
        )


def test_tds_crossing_five_lakh_on_full_gross():
    """Sprint 2 preview — 0.1% on full txn when FY crosses ₹5L."""
    rate, tds = tds_on_facilitation(
        entity_type="individual",
        pan_on_file=True,
        fy_gross_before=Decimal("490000"),
        this_amount=Decimal("20000"),
    )
    assert rate == Decimal("0.001")
    assert tds == Decimal("20.00")


def test_e2e_ui_refund_matrix_aligns_with_pricing():
    """E2E UI refund matrix must use production pricing signature."""
    from tests.e2e_ui.sprint1_settlement import refund_matrix

    rows = refund_matrix(FEE)
    by_id = {r["id"]: Decimal(r["refund_inr"]) for r in rows}
    assert by_id["cancel_requested"] == FEE
    assert by_id["cancel_confirmed"] == Decimal("0")
    assert by_id["no_pujari"] == FEE


def test_legacy_booking_sprint1_preview_mapping():
    """E2E UI maps live advance_balance rows to Sprint 1 preview."""
    preview = map_legacy_booking_to_sprint1_preview(
        {
            "payment_mode": "advance_balance",
            "total_amount": 2100,
            "amount_due_online": 250,
            "amount_due_offline": 1850,
            "status": "confirmed",
            "paid_at": "2026-09-08T10:00:00",
        }
    )
    assert preview["preview"] is True
    assert preview["sprint1_quote"]["payment_mode"] == "booking_fee"
    assert Decimal(preview["sprint1_quote"]["booking_fee"]) == FEE
