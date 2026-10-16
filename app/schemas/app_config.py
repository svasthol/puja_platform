"""Public mobile app config (§23.2 — P-APP-CONFIG)."""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel

from app.schemas.relationship_manager import RelationshipManagerPublic


class AppConfigResponse(BaseModel):
    night_bookings_enabled: bool
    instant_lead_hours: int
    advance_booking_amount: Decimal
    booking_fee: Decimal
    booking_fee_label: str
    full_online_enabled: bool = False
    # Public Razorpay key only (test or live). Empty when payments are not configured.
    razorpay_key_id: str | None = None
    payments_enabled: bool = False
    # Default RM for pre-booking muhurat help (name + phone only — not assigned priest).
    muhurat_help_contact: RelationshipManagerPublic | None = None
    # TDS / PAN launch flags (from .env — see spec/plans/TDS_RUNTIME_CONFIG.md).
    tds_accrual_enabled: bool = False
    pan_accept_gate_enabled: bool = False
    pujari_tax_profile_required_for_accept: bool = False
    pujari_fy_pan_gate_enabled: bool = False
    setu_pan_verify_configured: bool = False
