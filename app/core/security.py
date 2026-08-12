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


# ---- Per-app_context token TTL (P-ADMIN-AUTH) ------------------------------
def access_ttl_minutes(app_context: str) -> int:
    """Admin access tokens are short-lived; customer/pujari keep the default."""
    if app_context == "admin":
        return settings.ADMIN_ACCESS_TOKEN_EXPIRE_MINUTES
    return settings.ACCESS_TOKEN_EXPIRE_MINUTES


def refresh_ttl_days(app_context: str) -> int:
    """Admin refresh ≤ 1 day; customer/pujari keep 30. See SPEC_AMENDMENTS §19."""
    if app_context == "admin":
        return settings.ADMIN_REFRESH_TOKEN_EXPIRE_DAYS
    return settings.REFRESH_TOKEN_EXPIRE_DAYS


# ---- JWT (PyJWT) -----------------------------------------------------------
def create_access_token(*, subject: str, app_context: str, extra: dict | None = None) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "app_context": app_context,  # 'customer' | 'pujari' | 'admin'
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=access_ttl_minutes(app_context)),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def create_refresh_token(*, subject: str, app_context: str, jti: str) -> str:
    """Refresh token whose `jti` is the session lookup key (P-AUTH-FIX).

    The caller generates the jti (uuid4().hex) and stores it on the
    auth_sessions row: sessions are found by jti, then the presented token is
    verified against the stored bcrypt hash with verify_secret(). Equality
    lookup on hash_secret(token) can never match — bcrypt salts differ per call.
    """
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "app_context": app_context,
        "type": "refresh",
        "jti": jti,
        "iat": now,
        "exp": now + timedelta(days=refresh_ttl_days(app_context)),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def decode_token(token: str, *, verify_exp: bool = True) -> dict:
    """Raises jwt.PyJWTError subclasses on invalid/expired tokens.

    verify_exp=False is for logout only: revoking a session with an expired
    refresh token is harmless and keeps logout idempotent. Signature is
    ALWAYS verified.
    """
    return jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=["HS256"],
        options={"verify_exp": verify_exp},
    )


# ---- Razorpay webhook signature (constant-time compare) --------------------
def verify_razorpay_signature(body: bytes, signature: str) -> bool:
    if not settings.RAZORPAY_WEBHOOK_SECRET:
        return False
    expected = hmac.new(
        settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature or "")
