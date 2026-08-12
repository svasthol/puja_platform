"""Admin booking search + 360° detail (Sprint 4C — A-SEARCH, A-BOOKING-DETAIL)."""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.schemas.common import Page
from app.schemas.relationship_manager import RelationshipManagerPublic


class AdminBookingSummary(BaseModel):
    id: uuid.UUID
    status: str
    customer_phone: str
    customer_name: str
    puja_name: str
    scheduled_date: dt.date
    scheduled_time: dt.time
    total_amount: Decimal
    amount_due_online: Decimal
    payment_mode: str
    paid_at: dt.datetime | None
    assigned_pujari_name: str | None
    area_label: str | None
    created_at: dt.datetime


class AdminBookingListResponse(Page):
    bookings: list[AdminBookingSummary]


class AdminBookingCustomer(BaseModel):
    user_id: uuid.UUID
    full_name: str
    phone: str


class AdminBookingAddress(BaseModel):
    line1: str
    line2: str | None
    city: str
    pincode: str | None
    latitude: float | None
    longitude: float | None
    area_label: str | None


class AdminBookingPujari(BaseModel):
    id: uuid.UUID
    full_name: str
    phone: str
    rating_avg: Decimal
    rating_count: int


class AdminBookingStatusEvent(BaseModel):
    status: str
    changed_at: dt.datetime
    changed_by_user_id: uuid.UUID | None
    changed_by_name: str | None


class AdminBookingAssignment(BaseModel):
    id: uuid.UUID
    pujari_id: uuid.UUID
    pujari_name: str
    pujari_phone: str
    status: str
    offered_at: dt.datetime
    expires_at: dt.datetime
    responded_at: dt.datetime | None


class AdminBookingPayment(BaseModel):
    id: uuid.UUID
    amount: Decimal
    status: str
    gateway_txn_id: str | None
    idempotency_key: str
    created_at: dt.datetime


class AdminBookingRefund(BaseModel):
    id: uuid.UUID
    amount: Decimal
    status: str
    reason: str
    gateway_refund_id: str | None
    created_at: dt.datetime


class AdminBookingDispatch(BaseModel):
    dispatch_mode: str
    dispatch_starts_at: dt.datetime | None
    dispatch_deadline: dt.datetime | None
    intended_pujari_id: uuid.UUID | None


class AdminBookingDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    puja_name: str
    scheduled_date: dt.date
    scheduled_time: dt.time
    duration_minutes: int
    payment_mode: str
    total_amount: Decimal
    amount_due_online: Decimal
    amount_due_offline: Decimal
    balance_collected_at: dt.datetime | None
    paid_at: dt.datetime | None
    razorpay_order_id: str | None
    cancelled_at: dt.datetime | None
    created_at: dt.datetime
    updated_at: dt.datetime
    customer: AdminBookingCustomer
    address: AdminBookingAddress
    pujari: AdminBookingPujari | None
    dispatch: AdminBookingDispatch
    history: list[AdminBookingStatusEvent]
    assignments: list[AdminBookingAssignment]
    payments: list[AdminBookingPayment]
    refunds: list[AdminBookingRefund]
    relationship_manager: RelationshipManagerPublic | None


class AdminReassignRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    new_pujari_id: uuid.UUID
    change_reason: str | None = None


class AdminReassignResponse(BaseModel):
    booking_id: uuid.UUID
    old_pujari_id: uuid.UUID
    new_pujari_id: uuid.UUID
    assignment_id: uuid.UUID
    status: str
    reassigned_at: dt.datetime
