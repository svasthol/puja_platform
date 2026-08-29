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
    slug: Mapped[str | None] = mapped_column(String(150), unique=True)
    tagline: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    duration_minutes: Mapped[int | None] = mapped_column()
    default_price: Mapped[float] = mapped_column(Numeric(10, 2))
    price_max: Mapped[float | None] = mapped_column(Numeric(10, 2))
    display_order: Mapped[int] = mapped_column(SmallInteger, default=0)
    hero_media_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("puja_media.id"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))


class PujaAddon(Base):
    __tablename__ = "puja_addons"
    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    puja_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pujas.id"))
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    price: Mapped[float] = mapped_column(Numeric(10, 2))
    display_order: Mapped[int] = mapped_column(SmallInteger, default=0)
    image_media_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("puja_media.id"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class PujaContentItem(Base):
    __tablename__ = "puja_content_items"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    puja_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pujas.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(20))
    position: Mapped[int] = mapped_column(SmallInteger, default=0)
    locale: Mapped[str] = mapped_column(String(2), default="en")
    text: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class PujaCategoryI18n(Base):
    __tablename__ = "puja_category_i18n"

    category_id: Mapped[int] = mapped_column(
        ForeignKey("puja_categories.id", ondelete="CASCADE"), primary_key=True
    )
    locale: Mapped[str] = mapped_column(String(2), primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text)


class PujaI18n(Base):
    __tablename__ = "puja_i18n"

    puja_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pujas.id", ondelete="CASCADE"), primary_key=True
    )
    locale: Mapped[str] = mapped_column(String(2), primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    tagline: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)


class PujaAddonI18n(Base):
    __tablename__ = "puja_addon_i18n"

    addon_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("puja_addons.id", ondelete="CASCADE"), primary_key=True
    )
    locale: Mapped[str] = mapped_column(String(2), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)


class PujaMedia(Base):
    __tablename__ = "puja_media"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(20))
    entity_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True))
    s3_key: Mapped[str] = mapped_column(String(500))
    alt_text: Mapped[str | None] = mapped_column(String(200))
    position: Mapped[int] = mapped_column(SmallInteger, default=0)
    upload_status: Mapped[str] = mapped_column(String(20), default="pending")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


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


class PujariDocument(Base):
    __tablename__ = "pujari_documents"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    pujari_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pujaris.id", ondelete="CASCADE"))
    doc_type: Mapped[str] = mapped_column(String(30))
    file_url: Mapped[str] = mapped_column(String(500))
    version: Mapped[int] = mapped_column(SmallInteger, default=1)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    uploaded_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))


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
