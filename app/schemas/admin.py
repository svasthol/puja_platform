"""Admin schemas."""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field


class AdvanceAmountResponse(BaseModel):
    amount: Decimal
    currency: str
    updated_at: str | None = None


class AdvanceAmountUpdate(BaseModel):
    amount: Decimal = Field(ge=1, le=10000)
