"""Lookup / reference tables (SMALLSERIAL PKs)."""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StatusType(Base):
    __tablename__ = "status_types"
    __table_args__ = (UniqueConstraint("domain", "code"),)

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    domain: Mapped[str] = mapped_column(String(30))
    code: Mapped[str] = mapped_column(String(30))
    label: Mapped[str] = mapped_column(String(60))


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(30), unique=True)


class CancellationPolicy(Base):
    __tablename__ = "cancellation_policies"
    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    refund_pct_before_24h: Mapped[int] = mapped_column(SmallInteger)
    refund_pct_after_24h: Mapped[int] = mapped_column(SmallInteger)


class ServiceArea(Base):
    __tablename__ = "service_areas"
    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    city: Mapped[str] = mapped_column(String(80))
    zone_name: Mapped[str] = mapped_column(String(100))
    pincode: Mapped[str | None] = mapped_column(String(10))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class PujaCategory(Base):
    __tablename__ = "puja_categories"
    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    slug: Mapped[str | None] = mapped_column(String(120), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    display_order: Mapped[int] = mapped_column(SmallInteger, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    image_media_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("puja_media.id"), nullable=True
    )


class PlatformSetting(Base):
    __tablename__ = "platform_settings"
    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value_json: Mapped[dict] = mapped_column(JSONB)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
