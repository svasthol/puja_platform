"""
Security primitives — bcrypt (direct) for hashing, PyJWT for tokens.

Deliberately does NOT use passlib (unmaintained) or python-jose (abandoned).
See spec/STACK_VERSIONS.md.

FIX (hardening): the SHA-256 pre-hash digest is base64-encoded before bcrypt,
NOT passed as raw bytes. ~11% of raw SHA-256 digests contain a 0x00 byte;
bcrypt backends that use C-string length silently truncate at the first NUL,
reducing entropy. base64 keeps the value NUL-free and <72 bytes.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import get_settings

settings = get_settings()


# ---- OTP / refresh-token hashing (bcrypt direct) --------------------------
def _prehash(secret: str) -> bytes:
    """SHA-256 -> base64 -> ascii bytes. Fixed 44 bytes, NUL-free, <72 limit."""
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.b64encode(digest)  # 44 bytes, no NUL, safe for bcrypt


def hash_secret(secret: str) -> str:
    """Hash an OTP or refresh token. Returns str for a VARCHAR column."""
    return bcrypt.hashpw(_prehash(secret), bcrypt.gensalt()).decode("utf-8")


def verify_secret(secret: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prehash(secret), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---- JWT (PyJWT) -----------------------------------------------------------
def create_access_token(*, subject: str, app_context: str, extra: dict | None = None) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "app_context": app_context,  # 'customer' | 'pujari' | 'admin'
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def create_refresh_token(*, subject: str, app_context: str) -> str:
    """Opaque high-entropy refresh token (stored hashed, UNIQUE in DB)."""
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "app_context": app_context,
        "type": "refresh",
        "jti": base64.urlsafe_b64encode(hashlib.sha256(f"{subject}{now.timestamp()}".encode()).digest()).decode(),
        "iat": now,
        "exp": now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def decode_token(token: str) -> dict:
    """Raises jwt.PyJWTError subclasses on invalid/expired tokens."""
    return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])


# ---- Razorpay webhook signature (constant-time compare) --------------------
def verify_razorpay_signature(body: bytes, signature: str) -> bool:
    if not settings.RAZORPAY_WEBHOOK_SECRET:
        return False
    expected = hmac.new(
        settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature or "")
