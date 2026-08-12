"""Admin promo CRUD schemas (A-PROMO)."""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AdminPromoBase(BaseModel):
    code: str = Field(..., min_length=2, max_length=30)
    discount_pct: int = Field(..., ge=1, le=100)
    max_uses_per_user: int = Field(1, ge=1, le=100)
    valid_from: dt.datetime
    valid_until: dt.datetime
    is_active: bool = True

    @field_validator("code")
    @classmethod
    def normalize_code(cls, v: str) -> str:
        normalized = v.strip().upper()
        if not normalized:
            raise ValueError("code cannot be empty")
        return normalized

    @model_validator(mode="after")
    def valid_range(self) -> AdminPromoBase:
        if self.valid_until <= self.valid_from:
            raise ValueError("valid_until must be after valid_from")
        return self


class AdminPromoCreate(AdminPromoBase):
    pass


class AdminPromoUpdate(BaseModel):
    discount_pct: int | None = Field(None, ge=1, le=100)
    max_uses_per_user: int | None = Field(None, ge=1, le=100)
    valid_from: dt.datetime | None = None
    valid_until: dt.datetime | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> AdminPromoUpdate:
        if not any(
            v is not None
            for v in (
                self.discount_pct,
                self.max_uses_per_user,
                self.valid_from,
                self.valid_until,
                self.is_active,
            )
        ):
            raise ValueError("At least one field must be provided")
        return self


class AdminPromoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    discount_pct: int
    max_uses_per_user: int
    valid_from: dt.datetime
    valid_until: dt.datetime
    is_active: bool
    redemption_count: int = 0


class AdminPromoListResponse(BaseModel):
    promos: list[AdminPromoOut]
    next_cursor: str | None = None
