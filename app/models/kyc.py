"""Partner KYC ORM models (migration 020)."""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KycVerificationRequest(Base):
    __tablename__ = "kyc_verification_requests"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    pujari_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("pujaris.id", ondelete="CASCADE")
    )
    vendor: Mapped[str] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(16))
    vendor_request_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20))
    scope: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    nonce_hash: Mapped[str] = mapped_column(String(128))
    review_flags: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))


class KycIdentityRegistry(Base):
    __tablename__ = "kyc_identity_registry"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    digilocker_id_hash: Mapped[str] = mapped_column(String(128), unique=True)
    pujari_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("pujaris.id", ondelete="SET NULL"),
        nullable=True,
    )
    state: Mapped[str] = mapped_column(String(16))
    denied_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    denied_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    denied_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))


class KycConsent(Base):
    __tablename__ = "kyc_consents"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    pujari_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("pujaris.id", ondelete="CASCADE")
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("kyc_verification_requests.id", ondelete="CASCADE"),
    )
    purpose: Mapped[str] = mapped_column(String(64))
    text_version: Mapped[str] = mapped_column(String(32))
    consent_text_hash: Mapped[str] = mapped_column(String(128))
    granted_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
