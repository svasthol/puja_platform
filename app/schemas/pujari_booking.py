"""Pujari assigned bookings schemas (B-BOOKINGS)."""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from pydantic import BaseModel

from app.schemas.common import Page
from app.schemas.relationship_manager import RelationshipManagerPublic


class PujariBookingSummary(BaseModel):
    id: uuid.UUID
    status: str
    puja_name: str
    scheduled_date: dt.date
    scheduled_time: dt.time
    duration_minutes: int
    area_label: str | None
    payment_mode: str
    total_amount: Decimal
    amount_due_offline: Decimal
    reconfirm_pending: bool = False


class PujariBookingListResponse(Page):
    bookings: list[PujariBookingSummary]


class PujariBookingAddress(BaseModel):
    line1: str
    line2: str | None
    city: str
    pincode: str | None
    latitude: float | None
    longitude: float | None


class PujariBookingDetail(BaseModel):
    id: uuid.UUID
    status: str
    booking_class: str
    puja_name: str
    scheduled_date: dt.date
    scheduled_time: dt.time
    duration_minutes: int
    payment_mode: str
    total_amount: Decimal
    amount_due_online: Decimal
    amount_due_offline: Decimal
    balance_collected_at: dt.datetime | None
    area_label: str | None
    address: PujariBookingAddress
    map_url: str | None
    relationship_manager: RelationshipManagerPublic | None
    reconfirm_ping_sent_at: dt.datetime | None = None
    pujari_confirmed_at: dt.datetime | None = None
