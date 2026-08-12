"""Admin refund ops schemas (A-REFUND)."""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RefundOverrideRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    payment_id: uuid.UUID | None = None
    booking_id: uuid.UUID | None = None
    amount: Decimal = Field(gt=0)
    change_reason: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def require_payment_or_booking(self) -> RefundOverrideRequest:
        if self.payment_id is None and self.booking_id is None:
            raise ValueError("Provide payment_id or booking_id.")
        return self


class RefundOverrideResponse(BaseModel):
    refund_id: uuid.UUID
    payment_id: uuid.UUID
    booking_id: uuid.UUID
    amount: Decimal
    status: str


class AdminRefundQueueItem(BaseModel):
    id: uuid.UUID
    booking_id: uuid.UUID
    payment_id: uuid.UUID
    amount: Decimal
    status: str
    reason: str
    last_error: str | None
    attempt_count: int
    created_at: dt.datetime
    customer_phone: str | None
    customer_name: str | None


class AdminRefundListResponse(BaseModel):
    refunds: list[AdminRefundQueueItem]
    next_cursor: str | None = None
