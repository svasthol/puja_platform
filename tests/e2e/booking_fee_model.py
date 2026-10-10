"""
TEST ONLY — re-exports production pricing helpers for E2E contract tests.

Keeps tests/e2e aligned with app/services/pricing.py (single source of truth).
"""
from __future__ import annotations

from app.services.pricing import (
    BOOKING_FEE_LABEL,
    compute_booking_fee_amounts,
    customer_cancel_refund_amount,
    load_booking_fee,
    platform_charge_amount,
    refundable_platform_amount,
    tds_on_facilitation,
)

DEFAULT_BOOKING_FEE = __import__("decimal").Decimal("61.00")
DEFAULT_FEE_LABEL = BOOKING_FEE_LABEL


def compute_checkout_quote(
    *,
    puja_unit_price,
    addon_prices=None,
    booking_fee=DEFAULT_BOOKING_FEE,
    promo_pct: int = 0,
):
    """E2E UI contract wrapper around production pricing."""
    from decimal import Decimal

    addons = addon_prices or []
    subtotal = puja_unit_price + sum(addons, Decimal("0"))
    if promo_pct:
        subtotal = (subtotal * (Decimal(100 - promo_pct) / Decimal(100))).quantize(
            Decimal("0.01")
        )
    total, online, offline, fee = compute_booking_fee_amounts(subtotal, booking_fee)
    return {
        "payment_mode": "booking_fee",
        "booking_fee": str(fee),
        "booking_fee_label": DEFAULT_FEE_LABEL,
        "total_amount": str(total),
        "amount_due_online": str(online),
        "amount_due_offline": str(offline),
        "razorpay_amount_paise": int(fee * 100),
        "customer_pays_platform_inr": str(fee),
        "customer_pays_pujari_inr": str(total),
    }


def settlement_breakdown(**kwargs):
    """Minimal settlement view for E2E UI — delegates to quote math."""
    from decimal import Decimal

    total = Decimal(str(kwargs.get("total_amount", "0")))
    fee = Decimal(str(kwargs.get("booking_fee", DEFAULT_BOOKING_FEE)))
    paid = kwargs.get("paid_at", True)
    balance_collected = kwargs.get("balance_collected", False)
    offline_due = total
    collected = (
        Decimal(str(kwargs["balance_collected_amount"]))
        if kwargs.get("balance_collected_amount") is not None
        else (offline_due if balance_collected else Decimal("0"))
    )
    return {
        "payment_mode": kwargs.get("payment_mode", "booking_fee"),
        "status": kwargs.get("status", "requested"),
        "ledger": {
            "platform_revenue_inr": str(fee if paid else Decimal("0")),
            "pujari_collects_offline_inr": str(collected),
            "payment_splits_net_pujari_inr": "0",
        },
        "gates": {
            "complete_requires_balance_collected": offline_due > 0,
            "balance_collected": balance_collected,
        },
    }


def map_legacy_booking_to_sprint1_preview(row: dict):
    from decimal import Decimal

    total = Decimal(str(row.get("total_amount") or "0"))
    quote = compute_checkout_quote(puja_unit_price=total, booking_fee=DEFAULT_BOOKING_FEE)
    return {
        "preview": True,
        "note": f"Live API still uses {row.get('payment_mode')!r}.",
        "current_api": {
            "payment_mode": row.get("payment_mode"),
            "amount_due_online": row.get("amount_due_online"),
            "amount_due_offline": row.get("amount_due_offline"),
        },
        "sprint1_quote": quote,
        "sprint1_settlement": settlement_breakdown(
            total_amount=total,
            booking_fee=DEFAULT_BOOKING_FEE,
            status=row.get("status"),
            paid_at=bool(row.get("paid_at")),
            balance_collected=bool(row.get("balance_collected_at")),
        ),
    }
