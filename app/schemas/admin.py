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


class KycVendorOption(BaseModel):
    name: str
    label: str
    configured: bool


class KycVendorResponse(BaseModel):
    active_vendor: str
    source: Literal["console", "env"]
    env_default: str
    vendors: list[KycVendorOption]
    updated_at: str | None = None


class KycVendorUpdate(BaseModel):
    vendor: str = Field(min_length=1, max_length=40)
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


class DispatchPolicyResponse(BaseModel):
    """Launch dispatch + booking-gate keys from platform_settings (migrations 012/014)."""

    instant_lead_hours: int
    instant_dispatch_minutes: int
    advance_dispatch_start_hours: int
    advance_dispatch_fail_hours: int
    reoffer_cooldown_minutes: int
    dispatch_buffer_minutes: int
    immediate_dispatch_on_payment: bool
    instant_offer_ttl_seconds: int
    advance_offer_ttl_hours: int
    max_live_advance_offers_per_pujari: int
    rm_escalation_hours_no_accept: int
    rm_escalation_t24_hours: int
    max_offer_rounds: int
    urgency_escalation_lead_hours: int
    escalated_offer_ttl_seconds: int
    rebroadcast_on_urgency_flip: bool
    night_bookings_enabled: bool
    reconfirm_quiet_hours_start: str = Field(pattern=r"^([01]?\d|2[0-3]):[0-5]\d$")
    reconfirm_quiet_hours_end: str = Field(pattern=r"^([01]?\d|2[0-3]):[0-5]\d$")
    updated_at: str | None = None


class DispatchPolicyUpdate(BaseModel):
    instant_lead_hours: int = Field(ge=1, le=48)
    instant_dispatch_minutes: int = Field(ge=5, le=180)
    advance_dispatch_start_hours: int = Field(ge=1, le=48)
    advance_dispatch_fail_hours: int = Field(ge=1, le=24)
    reoffer_cooldown_minutes: int = Field(ge=0, le=240)
    dispatch_buffer_minutes: int = Field(ge=0, le=180)
    immediate_dispatch_on_payment: bool
    instant_offer_ttl_seconds: int = Field(ge=30, le=900)
    advance_offer_ttl_hours: int = Field(ge=1, le=72)
    max_live_advance_offers_per_pujari: int = Field(ge=1, le=50)
    rm_escalation_hours_no_accept: int = Field(ge=1, le=72)
    rm_escalation_t24_hours: int = Field(ge=1, le=72)
    # Omitted by older clients -> keep the stored value. 0 = retry until dispatch_deadline.
    max_offer_rounds: int | None = Field(default=None, ge=0, le=100)
    urgency_escalation_lead_hours: int | None = Field(default=None, ge=1, le=48)
    escalated_offer_ttl_seconds: int | None = Field(default=None, ge=60, le=7200)
    rebroadcast_on_urgency_flip: bool | None = None
    night_bookings_enabled: bool
    reconfirm_quiet_hours_start: str = Field(pattern=r"^([01]?\d|2[0-3]):[0-5]\d$")
    reconfirm_quiet_hours_end: str = Field(pattern=r"^([01]?\d|2[0-3]):[0-5]\d$")
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
