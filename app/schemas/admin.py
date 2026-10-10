"""Admin schemas."""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AdvanceAmountResponse(BaseModel):
    amount: Decimal
    currency: str
    updated_at: str | None = None


class AdvanceAmountUpdate(BaseModel):
    amount: Decimal = Field(ge=1, le=10000)
    change_reason: str | None = Field(default=None, max_length=300)


class BookingFeeResponse(BaseModel):
    amount: Decimal
    currency: str
    label: str
    updated_at: str | None = None


class BookingFeeUpdate(BaseModel):
    amount: Decimal = Field(ge=1, le=10000)
    label: str | None = Field(default=None, max_length=120)
    change_reason: str | None = Field(default=None, max_length=300)


class TdsFacilitationResponse(BaseModel):
    no_pan_rate_pct: Decimal
    pan_entity_rate_pct: Decimal
    individual_fy_threshold_inr: Decimal
    fy_turnover_warn_inr: Decimal
    fy_turnover_block_inr: Decimal
    always_taxed_entity_types: list[str]
    updated_at: str | None = None


class TdsFacilitationUpdate(BaseModel):
    no_pan_rate_pct: Decimal = Field(ge=0, le=100)
    pan_entity_rate_pct: Decimal = Field(ge=0, le=100)
    individual_fy_threshold_inr: Decimal = Field(ge=0, le=100_000_000)
    fy_turnover_warn_inr: Decimal = Field(ge=0, le=100_000_000)
    fy_turnover_block_inr: Decimal = Field(ge=0, le=100_000_000)
    always_taxed_entity_types: list[str] = Field(min_length=1, max_length=20)
    change_reason: str | None = Field(default=None, max_length=300)


# ---- Role management (P-ADMIN-SEED) ---------------------------------------
class RoleAssignRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    role: Literal["admin", "support"]
    change_reason: str | None = Field(default=None, max_length=300)


class UserRolesResponse(BaseModel):
    user_id: uuid.UUID
    roles: list[str]


class AdminMeResponse(BaseModel):
    """Session identity for the admin shell (A-ADMIN-UI role-gated nav)."""

    user_id: uuid.UUID
    phone: str
    roles: list[str]
    is_admin: bool = False
    is_support: bool = False


# ---- TOTP credential provisioning (P-ADMIN-AUTH) --------------------------
class CredentialProvisionResponse(BaseModel):
    """Returned ONCE at provisioning — the URI/secret are never retrievable again."""

    user_id: uuid.UUID
    provisioning_uri: str
    secret: str
    note: str = "Scan in an authenticator app now. This secret is shown only once."
