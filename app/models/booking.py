"""Booking & dispatch domain."""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    Date, DateTime, ForeignKey, Numeric, SmallInteger, String, Time,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SlotHold(Base):
    __tablename__ = "slot_holds"
    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    pujari_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pujaris.id"))  # NULL = "any pujari"
    slot_date: Mapped[dt.date] = mapped_column(Date)
    slot_time: Mapped[dt.time] = mapped_column(Time)
    held_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    released_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    converted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class Booking(Base):
    __tablename__ = "bookings"
    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    # pujari_id is TRIGGER-managed (trigger 3). Never write it from app code.
    pujari_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pujaris.id"))
    puja_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pujas.id"))
    address_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("addresses.id"))
    status_id: Mapped[int] = mapped_column(ForeignKey("status_types.id"))
    cancellation_policy_id: Mapped[int] = mapped_column(ForeignKey("cancellation_policies.id"))
    scheduled_date: Mapped[dt.date] = mapped_column(Date)
    scheduled_time: Mapped[dt.time] = mapped_column(Time)
    duration_minutes: Mapped[int] = mapped_column(SmallInteger, default=0)  # trigger-snapshotted
    cancelled_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    total_amount: Mapped[float] = mapped_column(Numeric(10, 2))
    # migration 002
    intended_pujari_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pujaris.id"))
    hold_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("slot_holds.id"))
    paid_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    dispatch_mode: Mapped[str] = mapped_column(String(10), default="broadcast")
    # migration 003
    payment_mode: Mapped[str] = mapped_column(String(20), default="full_online")
    amount_due_online: Mapped[float] = mapped_column(Numeric(10, 2))
    amount_due_offline: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    balance_collected_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    balance_collected_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    balance_collection_method: Mapped[str | None] = mapped_column(String(20))
    # migration 004 — set at checkout; returned on idempotent duplicate submit
    razorpay_order_id: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))


class BookingAddon(Base):
    __tablename__ = "booking_addons"
    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    booking_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bookings.id"))
    addon_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("puja_addons.id"))
    price_at_booking: Mapped[float] = mapped_column(Numeric(10, 2))


class BookingAssignment(Base):
    __tablename__ = "booking_assignments"
    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    booking_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bookings.id"))
    pujari_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pujaris.id"))
    status_id: Mapped[int] = mapped_column(ForeignKey("status_types.id"))
    offered_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    responded_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class BookingStatusHistory(Base):
    __tablename__ = "booking_status_history"
    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    booking_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bookings.id"))
    status_id: Mapped[int] = mapped_column(ForeignKey("status_types.id"))
    changed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    changed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))


class BookingDispatchState(Base):
    __tablename__ = "booking_dispatch_state"
    booking_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bookings.id"), primary_key=True)
    round: Mapped[int] = mapped_column(SmallInteger, default=0)
    radius_km: Mapped[float] = mapped_column(Numeric(5, 1), default=3.0)
    max_rounds: Mapped[int] = mapped_column(SmallInteger, default=4)
    last_dispatched: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    exhausted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
