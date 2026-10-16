"""Admin booking money read-only schemas (A-MONEY-READ)."""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from pydantic import BaseModel, Field


SETTLEMENT_PENDING_LABEL = "Collected online — settlement pending"


class AdminMoneyPaymentSplit(BaseModel):
    platform_fee: Decimal
    gst_amount: Decimal
    net_pujari_amount: Decimal


class AdminMoneyPayment(BaseModel):
    id: uuid.UUID
    amount: Decimal
    status: str
    gateway_txn_id: str | None = None
    created_at: dt.datetime
    settlement_label: str = Field(default=SETTLEMENT_PENDING_LABEL)
    split: AdminMoneyPaymentSplit | None = None


class AdminMoneyRefund(BaseModel):
    id: uuid.UUID
    payment_id: uuid.UUID
    amount: Decimal
    status: str
    reason: str
    gateway_refund_id: str | None = None
    created_at: dt.datetime


class AdminBookingMoneyResponse(BaseModel):
    booking_id: uuid.UUID
    payment_mode: str
    total_amount: Decimal
    amount_due_online: Decimal
    amount_due_offline: Decimal
    booking_fee: Decimal | None = None
    balance_collected_at: dt.datetime | None = None
    online_settlement_label: str = Field(default=SETTLEMENT_PENDING_LABEL)
    offline_balance_note: str | None = None
    total_paid_online: Decimal
    total_refunded_online: Decimal
    refundable_remaining_online: Decimal
    payments: list[AdminMoneyPayment]
    refunds: list[AdminMoneyRefund]
