"""Partner offer inbox schemas (P-LAUNCH-OFFERS)."""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from pydantic import BaseModel

from app.schemas.common import Page


class OfferCard(BaseModel):
    assignment_id: uuid.UUID
    booking_id: uuid.UUID
    expires_at: dt.datetime
    puja_name: str
    scheduled_date: dt.date
    scheduled_time: dt.time
    area_label: str | None
    payment_mode: str
    total_amount: Decimal
    amount_due_offline: Decimal
    booking_class: str
    urgency: str  # instant | advance — live UX (§21.6.E)
    urgency_escalated: bool


class OfferListResponse(Page):
    offers: list[OfferCard]
