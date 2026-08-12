"""Auth endpoints — OTP request/verify, refresh, logout.

Sprint 4-0 (P-ADMIN-AUTH-FIX + P-AUTH-FIX — SPEC_AMENDMENTS §19.1):

* app_context is a BODY field on OtpVerify, Literal["customer","pujari"] —
  the SMS OTP path can never mint an admin token (422 at the schema layer).
  Admin staff log in via TOTP (P-ADMIN-AUTH).
* Sessions are looked up by the refresh JWT's `jti` (stored on auth_sessions,
  migration 009), then the presented token is verified against the stored
  bcrypt hash. Equality lookup on hash_secret(token) never matches — bcrypt
  salts differ per call — which silently broke refresh AND logout.
* Refresh-token REUSE (a rotated/revoked jti presented again) is treated as
  theft: every live session for that user+app_context is revoked.
* OTP lockout lives in Redis (`otp_fail:{row_id}`), NOT the DB row: the
  request transaction rolls back on the 401, discarding any `attempts`
  increment — and an autonomous DB write would deadlock against our own
  FOR UPDATE row lock. Redis INCR is atomic, outlives the rollback, and the
  key TTL matches the OTP's own expiry. (Same bug class as
  IDEMPOTENT_BOOKING.md's "expired ORM object in the except block".)

OTP + verify are Redis rate-limited (per API_CONTRACTS). OTP is stored HASHED.
"""
from __future__ import annotations

import datetime as dt
import secrets
import uuid

import jwt as pyjwt
import structlog
from fastapi import APIRouter, Depends, HTTPException, status as http
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.redis_client import redis_delete, redis_expire, redis_incr
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_secret,
    refresh_ttl_days,
    verify_secret,
)
from app.db.engine import get_db_txn
from app.models.identity import AuthSession, OtpVerification, User
from app.schemas.auth import OtpRequest, OtpVerify, RefreshRequest, TokenPair
from app.services import sms_router

router = APIRouter(prefix="/auth", tags=["auth"])
log = structlog.get_logger()
settings = get_settings()


async def _rate_limit(key: str, limit: int, window_s: int) -> None:
    count = await redis_incr(key)
    if count == 1:
        await redis_expire(key, window_s)
    if count > limit:
        raise HTTPException(http.HTTP_429_TOO_MANY_REQUESTS, "Too many requests. Try later.")


# --------------------------------------------------------------------------- #
# OTP lockout counter (Redis — survives the request-transaction rollback)
# --------------------------------------------------------------------------- #
def _otp_fail_key(otp_row_id: uuid.UUID) -> str:
    return f"otp_fail:{otp_row_id}"


async def _otp_failures(otp_row_id: uuid.UUID) -> int:
    # INCR-with-0 would mutate; a plain GET via the resilient executor:
    from app.core.redis_client import redis_execute

    async def _op(r):  # noqa: ANN001
        val = await r.get(_otp_fail_key(otp_row_id))
        return int(val) if val is not None else 0

    return await redis_execute(_op)


async def _record_otp_failure(otp_row_id: uuid.UUID) -> int:
    """Atomic INCR; TTL bound to the OTP's own lifetime (+60s clock skew)."""
    key = _otp_fail_key(otp_row_id)
    count = await redis_incr(key)
    if count == 1:
        await redis_expire(key, settings.OTP_EXPIRE_MINUTES * 60 + 60)
    return count


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@router.post("/otp/request", status_code=http.HTTP_202_ACCEPTED)
async def otp_request(payload: OtpRequest, db: AsyncSession = Depends(get_db_txn)):
    await _rate_limit(f"otp_req:{payload.phone}", settings.OTP_RATE_LIMIT_PER_HOUR, 3600)
    otp = f"{secrets.randbelow(10**6):06d}"
    now = dt.datetime.now(dt.UTC)
    db.add(
        OtpVerification(
            id=uuid.uuid4(),
            user_id=None,
            phone=payload.phone,
            otp_hash=hash_secret(otp),
            purpose="login",
            attempts=0,
            expires_at=now + dt.timedelta(minutes=settings.OTP_EXPIRE_MINUTES),
            created_at=now,
        )
    )
    sms_result = await sms_router.send_otp_sms(payload.phone, otp)
    log.info(
        "otp_issued",
        phone=payload.phone,
        sms_sent=sms_result.sent,
        sms_provider=sms_result.provider,
        **({"otp_dev_only": otp} if settings.DEBUG and not sms_result.sent else {}),
    )
    body: dict = {
        "status": "otp_sent",
        "sms_sent": sms_result.sent,
        "sms_provider": sms_result.provider,
    }
    # Dev ergonomics: Swagger / E2E Log can read the code when SMS did not send.
    if settings.DEBUG and not sms_result.sent:
        body["otp_dev_only"] = otp
    return body


@router.post("/otp/verify", response_model=TokenPair)
async def otp_verify(payload: OtpVerify, db: AsyncSession = Depends(get_db_txn)):
    await _rate_limit(f"otp_vfy:{payload.phone}", 10, 3600)
    now = dt.datetime.now(dt.UTC)
    row = (
        await db.execute(
            select(OtpVerification)
            .where(
                OtpVerification.phone == payload.phone,
                OtpVerification.verified_at.is_(None),
                OtpVerification.expires_at > now,
            )
            .order_by(OtpVerification.created_at.desc())
            .with_for_update()
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(http.HTTP_400_BAD_REQUEST, "No active OTP. Request a new one.")

    # Lockout: Redis counter (per OTP row) — the DB `attempts` column cannot be
    # the enforcement point because the 401 below rolls the transaction back.
    failures = await _otp_failures(row.id)
    if failures >= settings.OTP_MAX_ATTEMPTS or row.attempts >= settings.OTP_MAX_ATTEMPTS:
        raise HTTPException(http.HTTP_400_BAD_REQUEST, "Too many attempts. Request a new OTP.")

    if not verify_secret(payload.otp, row.otp_hash):
        count = await _record_otp_failure(row.id)
        log.warning("otp_verify_failed", phone=payload.phone, failures=count)
        raise HTTPException(http.HTTP_401_UNAUTHORIZED, "Incorrect OTP.")

    row.verified_at = now
    row.attempts = min(failures, settings.OTP_MAX_ATTEMPTS)  # persist for audit (commits now)
    await redis_delete(_otp_fail_key(row.id))

    # upsert user
    user = (await db.execute(select(User).where(User.phone == payload.phone))).scalar_one_or_none()
    if user is None:
        user = User(
            id=uuid.uuid4(),
            full_name="New User",
            phone=payload.phone,
            email=None,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        db.add(user)
        await db.flush()

    # app_context comes from the validated body — Literal["customer","pujari"].
    # 'admin' is impossible here by construction (P-ADMIN-AUTH-FIX).
    return _issue_token_pair(
        db, user_id=user.id, app_context=payload.app_context, device_id=None, now=now
    )


def _issue_token_pair(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    app_context: str,
    device_id: uuid.UUID | None,
    now: dt.datetime,
) -> TokenPair:
    """Mint access+refresh and persist the session (jti = lookup key)."""
    jti = uuid.uuid4().hex
    access = create_access_token(subject=str(user_id), app_context=app_context)
    refresh = create_refresh_token(subject=str(user_id), app_context=app_context, jti=jti)
    db.add(
        AuthSession(
            id=uuid.uuid4(),
            user_id=user_id,
            device_id=device_id,
            app_context=app_context,
            refresh_token_hash=hash_secret(refresh),
            refresh_jti=jti,
            issued_at=now,
            expires_at=now + dt.timedelta(days=refresh_ttl_days(app_context)),
        )
    )
    return TokenPair(access_token=access, refresh_token=refresh)


async def _resolve_refresh_session(
    db: AsyncSession, token: str, *, verify_exp: bool
) -> tuple[dict, AuthSession | None]:
    """Decode the refresh JWT and load its session row (FOR UPDATE) by jti."""
    try:
        claims = decode_token(token, verify_exp=verify_exp)
    except pyjwt.PyJWTError:
        raise HTTPException(http.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    if claims.get("type") != "refresh":
        raise HTTPException(http.HTTP_401_UNAUTHORIZED, "Not a refresh token")
    jti = claims.get("jti")
    if not jti:
        # Tokens minted before migration 009 carry a derived jti that was never
        # stored — those sessions were unrefreshable anyway. Force re-login.
        raise HTTPException(http.HTTP_401_UNAUTHORIZED, "Session revoked or unknown")

    sess = (
        await db.execute(
            select(AuthSession).where(AuthSession.refresh_jti == jti).with_for_update()
        )
    ).scalar_one_or_none()
    return claims, sess


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db_txn)):
    claims, sess = await _resolve_refresh_session(db, payload.refresh_token, verify_exp=True)
    now = dt.datetime.now(dt.UTC)

    if sess is None:
        raise HTTPException(http.HTTP_401_UNAUTHORIZED, "Session revoked or unknown")

    if sess.revoked_at is not None:
        # A previously-rotated (or logged-out) token is being replayed. Treat as
        # theft: kill every live session for this user+context so the attacker's
        # rotated descendant dies too (standard reuse-detection response).
        await db.execute(
            update(AuthSession)
            .where(
                AuthSession.user_id == sess.user_id,
                AuthSession.app_context == sess.app_context,
                AuthSession.revoked_at.is_(None),
            )
            .values(revoked_at=now, revoked_reason="refresh_reuse")
        )
        log.warning(
            "refresh_token_reuse_detected",
            user_id=str(sess.user_id),
            app_context=sess.app_context,
        )
        raise HTTPException(http.HTTP_401_UNAUTHORIZED, "Session revoked or unknown")

    if sess.expires_at <= now:
        raise HTTPException(http.HTTP_401_UNAUTHORIZED, "Session expired")

    if not verify_secret(payload.refresh_token, sess.refresh_token_hash):
        # jti matched but the token bytes don't — forged/corrupted token.
        log.warning("refresh_hash_mismatch", user_id=str(sess.user_id))
        raise HTTPException(http.HTTP_401_UNAUTHORIZED, "Invalid refresh token")

    # Rotate: revoke old, issue new (new jti). Sliding expiry, matching the
    # pre-existing behaviour; per-context TTL caps land with P-ADMIN-AUTH.
    sess.revoked_at = now
    sess.revoked_reason = "rotated"
    return _issue_token_pair(
        db,
        user_id=sess.user_id,
        app_context=sess.app_context,
        device_id=sess.device_id,
        now=now,
    )


@router.post("/logout")
async def logout(payload: RefreshRequest, db: AsyncSession = Depends(get_db_txn)):
    # verify_exp=False: revoking with an expired token is harmless and keeps
    # logout idempotent. The signature is still verified.
    _claims, sess = await _resolve_refresh_session(db, payload.refresh_token, verify_exp=False)
    if sess is not None and sess.revoked_at is None:
        if not verify_secret(payload.refresh_token, sess.refresh_token_hash):
            raise HTTPException(http.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
        sess.revoked_at = dt.datetime.now(dt.UTC)
        sess.revoked_reason = "logout"
    # Unknown or already-revoked session → still 200: logout is idempotent.
    return {"status": "logged_out"}
