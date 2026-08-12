"""Public mobile app config (§23.2 — P-APP-CONFIG)."""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel

from app.schemas.relationship_manager import RelationshipManagerPublic


class AppConfigResponse(BaseModel):
    night_bookings_enabled: bool
    instant_lead_hours: int
    advance_booking_amount: Decimal
    # Public Razorpay key only (test or live). Empty when payments are not configured.
    razorpay_key_id: str | None = None
    payments_enabled: bool = False
    # Default RM for pre-booking muhurat help (name + phone only — not assigned priest).
    muhurat_help_contact: RelationshipManagerPublic | None = None
