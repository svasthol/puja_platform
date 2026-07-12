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


class SlotHoldResponse(BaseModel):
    hold_id: uuid.UUID
    expires_at: dt.datetime
    pujari_id: uuid.UUID | None = None
    server_time: dt.datetime


class QuotePaymentOption(BaseModel):
    amount_due_online: Decimal
    amount_due_offline: Decimal
    label: str


class CheckoutQuote(BaseModel):
    total_amount: Decimal
    advance_amount: Decimal
    full_online: QuotePaymentOption
    advance_balance: QuotePaymentOption


class BookingCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    hold_id: uuid.UUID
    puja_id: uuid.UUID
    address_id: uuid.UUID
    addon_ids: list[uuid.UUID] = Field(default_factory=list)
    promo_code: str | None = None
    payment_mode: Literal["full_online", "advance_balance"]


class BookingCreateResponse(BaseModel):
    booking_id: uuid.UUID
    razorpay_order_id: str | None = None  # None only for rows created before migration 004
    amount_due_online: Decimal
    amount_due_offline: Decimal
    total_amount: Decimal
    payment_mode: str
    hold_expires_at: dt.datetime
    idempotent: bool = False


class CancelResponse(BaseModel):
    booking_id: uuid.UUID
    status: str
    refund_amount: Decimal
    refund_eta: str


class DispatchChoice(BaseModel):
    action: Literal["broadcast", "cancel"]


class BalanceCollected(BaseModel):
    method: Literal["cash", "upi_direct"]
