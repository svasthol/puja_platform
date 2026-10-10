"""Admin TDS compliance surfaces (§0.S — S4/S7/S8/S9)."""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TdsAccrualIntentRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    intent_id: uuid.UUID
    booking_id: uuid.UUID
    pujari_id: uuid.UUID
    status: str
    park_reason: str | None
    gross_amount: Decimal
    collected_at: str
    snapshot_entity_type: str | None
    snapshot_pan_on_file: bool | None
    attempt_count: int
    last_error: str | None
    created_at: str


class TdsPujariReadinessRow(BaseModel):
    pujari_id: uuid.UUID
    entity_type: str | None
    pan_on_file: bool
    pan_status: str
    parked_intents: int
    pending_intents: int


class TdsComplianceBacklogResponse(BaseModel):
    parked_count: int
    pending_count: int
    failed_count: int
    intents: list[TdsAccrualIntentRow]
    pujari_readiness: list[TdsPujariReadinessRow]


class TdsFyReconcileRow(BaseModel):
    pujari_id: uuid.UUID
    fy_start: str
    kind: Literal["gross_facilitation", "tds_accrued"] = "gross_facilitation"
    accumulator_gross: Decimal
    ledger_net: Decimal
    drift: Decimal


class TdsFyReconcileResponse(BaseModel):
    green: bool
    rows: list[TdsFyReconcileRow]


class TdsCorrectOfflineCollectionRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    action: Literal["clear", "set_amount"]
    amount: Decimal | None = None
    change_reason: str = Field(min_length=3, max_length=500)


class TdsCorrectOfflineCollectionResponse(BaseModel):
    booking_id: uuid.UUID
    balance_collected_amount: Decimal | None
    balance_collected_at: str | None
    tds_reversal: dict | None = None
    tds_requeued: bool = False


class TdsBookingFindingRow(BaseModel):
    booking_id: uuid.UUID
    issue_code: str
    total_amount_inr: str
    tds_liability_inr: str
    intent_status: str | None = None
    park_reason: str | None = None
    last_error: str | None = None


class TdsFyTroubleshootTaxSection(BaseModel):
    card_tds_accrued_inr: Decimal
    ledger_tds_net_inr: Decimal
    drift_inr: Decimal
    tds_at_accept_from_bookings_inr: Decimal
    tds_on_collected_with_ledger_inr: Decimal
    status: Literal["match", "fixable", "manual", "accrual_disabled"]
    green: bool


class TdsFyTroubleshootGrossSection(BaseModel):
    card_gross_facilitation_inr: Decimal
    ledger_taxable_base_net_inr: Decimal
    drift_inr: Decimal
    turnover_at_accept_from_bookings_inr: Decimal
    collected_gross_inr: Decimal
    status: Literal["match", "expected_v3", "investigate", "no_tax_year_row"]
    informational_only: bool


class TdsFyTroubleshootResponse(BaseModel):
    pujari_id: uuid.UUID
    fy_start: str
    fy_end_exclusive: str
    accrual_enabled: bool
    tax: TdsFyTroubleshootTaxSection
    gross: TdsFyTroubleshootGrossSection
    booking_findings: list[TdsBookingFindingRow]
    messages: list[str]
    action_required: bool
    safe_fix_available: bool


class TdsFyTroubleshootFixRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    change_reason: str = Field(min_length=3, max_length=500)


class TdsFyTroubleshootFixResponse(BaseModel):
    change_reason: str
    reconciled_intents: int = 0
    requeued_booking_ids: list[str]
    skipped: list[dict[str, str]]
    worker_stats: dict[str, int]
    troubleshoot_after: TdsFyTroubleshootResponse
