"""Booking, hold, checkout schemas."""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SlotHoldRequest(BaseModel):
    pujari_id: uuid.UUID | None = None  # omitted = "any pujari" broadcast
    date: dt.date
    time: dt.time


class GateWarning(BaseModel):
    code: str
    message: str


class SlotHoldResponse(BaseModel):
    hold_id: uuid.UUID
    expires_at: dt.datetime
    pujari_id: uuid.UUID | None = None
    server_time: dt.datetime
    # Advisory only — POST /v1/bookings is authoritative (§21.6.A).
    advisory_booking_class: Literal["instant", "advance"] | None = None
    gate_warnings: list[GateWarning] = Field(default_factory=list)


class QuotePaymentOption(BaseModel):
    amount_due_online: Decimal
    amount_due_offline: Decimal
    label: str


class CheckoutQuote(BaseModel):
    total_amount: Decimal
    payment_mode: Literal["booking_fee"] = "booking_fee"
    booking_fee: Decimal
    booking_fee_label: str
    amount_due_online: Decimal
    amount_due_offline: Decimal
    razorpay_amount: Decimal
    # Legacy fields retained for backward-compatible clients during rollout.
    advance_amount: Decimal | None = None
    full_online: QuotePaymentOption | None = None
    advance_balance: QuotePaymentOption | None = None


class BookingCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    hold_id: uuid.UUID
    puja_id: uuid.UUID
    address_id: uuid.UUID
    addon_ids: list[uuid.UUID] = Field(default_factory=list)
    promo_code: str | None = None
    payment_mode: Literal["booking_fee", "full_online", "advance_balance"] = "booking_fee"


class BookingCreateResponse(BaseModel):
    booking_id: uuid.UUID
    booking_class: Literal["instant", "advance"]
    razorpay_order_id: str | None = None  # None only for rows created before migration 004
    amount_due_online: Decimal
    amount_due_offline: Decimal
    total_amount: Decimal
    booking_fee: Decimal = Decimal("0")
    booking_fee_label: str | None = None
    razorpay_amount: Decimal
    payment_mode: str
    hold_expires_at: dt.datetime
    idempotent: bool = False


class CancelResponse(BaseModel):
    booking_id: uuid.UUID
    status: str
    refund_amount: Decimal
    refund_eta: str


class PujariCancelResponse(BaseModel):
    booking_id: uuid.UUID
    status: str


class DispatchChoice(BaseModel):
    action: Literal["broadcast", "cancel"]


class BalanceCollected(BaseModel):
    method: Literal["cash", "upi_direct"]
    amount: Decimal | None = None


class TdsAccrualInfo(BaseModel):
    accrual_enabled: bool
    skipped: bool = False
    idempotent: bool = False
    tds_rate: str | None = None
    tds_amount: str | None = None
    fy_gross_after: str | None = None
    fy_threshold_inr: str | None = None
    threshold_remaining_inr: str | None = None
    message: str | None = None
    message_code: str | None = None


class BalanceCollectedResponse(BaseModel):
    status: Literal["collected", "already_collected"]
    method: Literal["cash", "upi_direct"] | None = None
    amount: Decimal | None = None
    tds: TdsAccrualInfo | None = None
