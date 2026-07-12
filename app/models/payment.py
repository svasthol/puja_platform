"""Payments, splits, refunds domain."""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import DateTime, ForeignKey, Numeric, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    booking_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bookings.id"))
    amount: Mapped[float] = mapped_column(Numeric(10, 2))
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True)
    gateway_txn_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))


class PaymentSplit(Base):
    __tablename__ = "payment_splits"
    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    payment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payments.id"), unique=True)
    platform_fee: Mapped[float] = mapped_column(Numeric(10, 2))
    gst_amount: Mapped[float] = mapped_column(Numeric(10, 2))
    # net_pujari_amount is TRIGGER-computed (trigger 1). Never write from app.
    net_pujari_amount: Mapped[float] = mapped_column(Numeric(10, 2), default=0)


class Refund(Base):
    __tablename__ = "refunds"
    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    payment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payments.id"))
    booking_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bookings.id"))
    amount: Mapped[float] = mapped_column(Numeric(10, 2))
    reason: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    gateway_refund_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    attempt_count: Mapped[int] = mapped_column(SmallInteger, default=0)
    next_attempt_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
