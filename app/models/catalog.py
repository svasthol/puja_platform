"""Pujari profile & catalog domain."""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Numeric, SmallInteger, String, Text, Time,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Puja(Base):
    __tablename__ = "pujas"
    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("puja_categories.id"))
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text)
    duration_minutes: Mapped[int | None] = mapped_column()
    default_price: Mapped[float] = mapped_column(Numeric(10, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class PujaAddon(Base):
    __tablename__ = "puja_addons"
    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    puja_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pujas.id"))
    name: Mapped[str] = mapped_column(String(100))
    price: Mapped[float] = mapped_column(Numeric(10, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Pujari(Base):
    __tablename__ = "pujaris"
    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True)
    bio: Mapped[str | None] = mapped_column(Text)
    years_experience: Mapped[int | None] = mapped_column(SmallInteger)
    verification_status: Mapped[str] = mapped_column(String(20), default="pending")
    rating_avg: Mapped[float] = mapped_column(Numeric(3, 2), default=0)
    rating_count: Mapped[int] = mapped_column(default=0)
    is_online: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))


class PujariAvailability(Base):
    __tablename__ = "pujari_availability"
    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    pujari_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pujaris.id"))
    day_of_week: Mapped[int] = mapped_column(SmallInteger)
    start_time: Mapped[dt.time] = mapped_column(Time)
    end_time: Mapped[dt.time] = mapped_column(Time)


class PujariUnavailability(Base):
    __tablename__ = "pujari_unavailability"
    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    pujari_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pujaris.id"))
    unavailable_date: Mapped[dt.date] = mapped_column(Date)
    reason: Mapped[str | None] = mapped_column(String(100))


class PujariLiveLocation(Base):
    __tablename__ = "pujari_live_location"
    pujari_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pujaris.id"), primary_key=True)
    latitude: Mapped[float] = mapped_column(Numeric(9, 6))
    longitude: Mapped[float] = mapped_column(Numeric(9, 6))
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))


class PujariServiceArea(Base):
    __tablename__ = "pujari_service_areas"
    pujari_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pujaris.id"), primary_key=True)
    service_area_id: Mapped[int] = mapped_column(ForeignKey("service_areas.id"), primary_key=True)
