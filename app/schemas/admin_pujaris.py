"""Admin partner directory + pricing schemas (Sprint 4B — A-PUJARI-PRICING)."""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

VerificationStatus = Literal["pending", "verified", "rejected"]


class AdminPujariSummary(BaseModel):
    id: uuid.UUID
    full_name: str
    phone: str
    verification_status: VerificationStatus
    rating_avg: Decimal
    rating_count: int
    years_experience: int | None = None
    pricing_count: int
    created_at: dt.datetime


class AdminPujariListResponse(BaseModel):
    pujaris: list[AdminPujariSummary]
    next_cursor: str | None = None


class PujariPricingRow(BaseModel):
    puja_id: uuid.UUID
    puja_name: str
    puja_slug: str
    default_price: Decimal
    price_max: Decimal | None = None
    base_price: Decimal | None = None


class PujariPricingResponse(BaseModel):
    pujari_id: uuid.UUID
    full_name: str
    phone: str
    verification_status: VerificationStatus
    items: list[PujariPricingRow]


class PujariPricingItemInput(BaseModel):
    puja_id: uuid.UUID
    base_price: Decimal = Field(ge=0)


class PujariPricingReplaceRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    items: list[PujariPricingItemInput] = Field(default_factory=list, max_length=500)
    change_reason: str | None = Field(default=None, max_length=300)
