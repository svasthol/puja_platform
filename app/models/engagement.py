"""Engagement & growth domain (promos, notifications, chat)."""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PromoCode(Base):
    __tablename__ = "promo_codes"
    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    discount_pct: Mapped[int] = mapped_column(SmallInteger)
    max_uses_per_user: Mapped[int] = mapped_column(SmallInteger, default=1)
    valid_from: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class PromoRedemption(Base):
    __tablename__ = "promo_redemptions"
    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    promo_code_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("promo_codes.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    booking_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bookings.id"))
    redeemed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    app_context: Mapped[str] = mapped_column(String(10))
    related_type: Mapped[str | None] = mapped_column(String(30))
    related_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    title: Mapped[str] = mapped_column(String(150))
    body: Mapped[str | None] = mapped_column(Text)
    read_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))


class ChatConversation(Base):
    __tablename__ = "chat_conversations"
    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    booking_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bookings.id"), unique=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chat_conversations.id"))
    sender_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    message_type: Mapped[str] = mapped_column(String(10), default="text")
    media_url: Mapped[str | None] = mapped_column(String(500))
    read_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
