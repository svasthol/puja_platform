"""
TEST ONLY — Sprint 1 settlement helpers for E2E UI (no app imports).
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

from tests.e2e.booking_fee_model import (  # noqa: E402
    DEFAULT_BOOKING_FEE,
    compute_checkout_quote,
    map_legacy_booking_to_sprint1_preview,
    refundable_platform_amount,
    settlement_breakdown,
)

REFUND_SCENARIOS = [
    {
        "id": "no_pujari",
        "label": "No pujari found",
        "status": "failed_no_pujari",
        "reason": "no_pujari",
        "refund_pct": 100,
    },
    {
        "id": "cancel_requested",
        "label": "Customer cancel (requested)",
        "status": "requested",
        "reason": "customer_cancel",
        "refund_pct": 100,
    },
    {
        "id": "cancel_confirmed",
        "label": "Customer cancel (confirmed)",
        "status": "confirmed",
        "reason": "customer_cancel",
        "refund_pct": 0,
    },
    {
        "id": "pujari_rebroadcast",
        "label": "Pujari cancel → rebroadcast",
        "status": "requested",
        "reason": "pujari_cancel_rebroadcast",
        "refund_pct": 0,
    },
    {
        "id": "platform_terminate",
        "label": "Platform terminate",
        "status": "cancelled",
        "reason": "platform_terminate",
        "refund_pct": 100,
    },
]


def load_booking_fee_from_settings(db_url: str) -> Decimal:
    """Read configured fee from platform_settings or advance_booking_amount fallback."""
    import os

    import psycopg
    from dotenv import load_dotenv
    from psycopg.rows import dict_row

    load_dotenv(PROJECT_ROOT / ".env")
    url = db_url or os.environ.get("DATABASE_URL", "")
    if not url:
        return DEFAULT_BOOKING_FEE
    url = url.replace("postgresql+psycopg://", "postgresql://").replace(
        "postgresql+psycopg2://", "postgresql://"
    )
    try:
        with psycopg.connect(url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT value_json FROM platform_settings WHERE key = 'booking_fee'"
                )
                row = cur.fetchone()
                if row and row.get("value_json"):
                    amt = row["value_json"].get("amount")
                    if amt is not None:
                        return Decimal(str(amt))
    except Exception:
        pass
    return DEFAULT_BOOKING_FEE


def sprint1_quote(
    *,
    puja_price: Decimal,
    addon_total: Decimal = Decimal("0"),
    booking_fee: Decimal | None = None,
    db_url: str = "",
) -> dict[str, Any]:
    fee = booking_fee if booking_fee is not None else load_booking_fee_from_settings(db_url)
    unit = puja_price - addon_total if addon_total else puja_price
    quote = compute_checkout_quote(
        puja_unit_price=unit,
        addon_prices=[addon_total] if addon_total else None,
        booking_fee=fee,
    )
    quote["simulated"] = True
    quote["implementation_status"] = "live"
    return quote


def _scenario_status_code(status: str) -> str:
    """Map E2E scenario status to booking status_code for refund helpers."""
    if status in ("payment_pending", "requested", "confirmed"):
        return status
    return "requested"


def refund_matrix(booking_fee: Decimal = DEFAULT_BOOKING_FEE) -> list[dict[str, Any]]:
    rows = []
    for s in REFUND_SCENARIOS:
        amt = refundable_platform_amount(
            booking_fee=booking_fee,
            amount_due_online=Decimal("0"),
            payment_mode="booking_fee",
            status_code=_scenario_status_code(s["status"]),
            reason=s["reason"],
        )
        rows.append({**s, "refund_inr": str(amt)})
    return rows


def booking_settlement_view(row: dict[str, Any]) -> dict[str, Any]:
    """Full settlement view for one booking row from test_db."""
    total = Decimal(str(row.get("total_amount") or "0"))
    fee_col = row.get("booking_fee")
    if fee_col is not None:
        fee = Decimal(str(fee_col))
        mode = str(row.get("payment_mode") or "booking_fee")
        implementation = "live" if mode == "booking_fee" else "legacy_mode"
    else:
        fee = load_booking_fee_from_settings("")
        mode = "booking_fee"
        implementation = "preview"

    paid = bool(row.get("paid_at"))
    balance_collected = bool(row.get("balance_collected_at"))
    bal_amt = row.get("balance_collected_amount")

    breakdown = settlement_breakdown(
        total_amount=total,
        booking_fee=fee,
        payment_mode=mode,
        status=str(row.get("status") or ""),
        paid_at=paid,
        balance_collected=balance_collected,
        balance_collected_amount=Decimal(str(bal_amt)) if bal_amt is not None else None,
    )

    preview = None
    if row.get("payment_mode") != "booking_fee":
        preview = map_legacy_booking_to_sprint1_preview(row)

    payment_amount = row.get("payment_amount")
    return {
        "booking_id": row.get("booking_id"),
        "implementation": implementation,
        "current": {
            "payment_mode": row.get("payment_mode"),
            "total_amount": row.get("total_amount"),
            "amount_due_online": row.get("amount_due_online"),
            "amount_due_offline": row.get("amount_due_offline"),
            "booking_fee": row.get("booking_fee"),
            "status": row.get("status"),
            "paid_at": row.get("paid_at"),
            "payment_amount": payment_amount,
            "balance_collected_at": row.get("balance_collected_at"),
        },
        "settlement": breakdown,
        "refund_matrix": refund_matrix(fee),
        "sprint1_preview": preview,
    }
