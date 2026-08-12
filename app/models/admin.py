"""Admin control-plane domain — audit log + staff credentials (migration 009)."""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import BigInteger, DateTime, ForeignKey, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AdminAuditLog(Base):
    """Append-only (REVOKE UPDATE/DELETE from puja_app — migration 009 + apply_grants.sql).

    Successful admin mutations INSERT a row in the same transaction; failed
    attempts are logged via structlog only (an in-txn row would roll back with
    the failed mutation). PII reads log action='read' (DPDP).
    """

    __tablename__ = "admin_audit_log"
    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(30))
    entity_type: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    before_json: Mapped[dict | None] = mapped_column(JSONB)
    after_json: Mapped[dict | None] = mapped_column(JSONB)
    change_reason: Mapped[str | None] = mapped_column(String(300))
    ip: Mapped[str | None] = mapped_column(INET)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))


class AdminCredential(Base):
    """TOTP credential for admin/support staff (P-ADMIN-AUTH).

    totp_secret_enc is app-layer ciphertext (Fernet/AES-GCM, TOTP_ENC_KEY from
    the secrets manager) — TOTP verification needs the plaintext, so it cannot
    be hashed like OTPs. activated_at is NULL until the user proves possession
    with a valid code; last_used_step blocks same-code replay within a 30s step.
    """

    __tablename__ = "admin_credentials"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    totp_secret_enc: Mapped[str] = mapped_column(Text)
    key_version: Mapped[int] = mapped_column(SmallInteger, default=1)
    enrolled_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    activated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_step: Mapped[int] = mapped_column(BigInteger, default=0)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
