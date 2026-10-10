"""Admin booking TDS / collection read-only (ops debug without SQL)."""
from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel


class AdminBookingTdsResponse(BaseModel):
    booking_id: uuid.UUID
    pujari_id: uuid.UUID | None
    accrual_enabled: bool

    balance_collected_at: str | None
    balance_collected_amount_inr: Decimal | None

    accept_tds_snapshot_at: str | None
    tds_liability_inr: Decimal | None
    tds_taxable_base_inr: Decimal | None
    tds_rate_applied: str | None
    tds_collected_online_inr: Decimal | None

    ledger_accrual_present: bool
    ledger_fy_start: str | None
    ledger_taxable_base_inr: Decimal | None
    ledger_tds_amount_inr: Decimal | None

    accrual_intent_status: str | None
    accrual_intent_park_reason: str | None
    accrual_intent_last_error: str | None
    accrual_intent_attempt_count: int | None

    ops_status: str
    hints: list[str]
