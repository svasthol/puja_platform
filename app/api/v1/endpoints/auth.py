"""Auth endpoints — OTP request/verify, refresh, logout.

OTP + verify are Redis rate-limited (per API_CONTRACTS). OTP is stored HASHED.
Lockout: otp_verifications.attempts increments per failure; at 5 -> fresh OTP.
"""
from __future__ import annotations

import datetime as dt
import secrets
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, status as http
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.redis_client import redis_expire, redis_incr
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_secret,
    verify_secret,
)
from app.db.engine import get_db, get_db_txn
from app.models.identity import AuthSession, OtpVerification, User
from app.schemas.auth import OtpRequest, OtpVerify, RefreshRequest, TokenPair

router = APIRouter(prefix="/auth", tags=["auth"])
log = structlog.get_logger()
settings = get_settings()


async def _rate_limit(key: str, limit: int, window_s: int) -> None:
    count = await redis_incr(key)
    if count == 1:
        await redis_expire(key, window_s)
    if count > limit:
        raise HTTPException(http.HTTP_429_TOO_MANY_REQUESTS, "Too many requests. Try later.")


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
    # send via MSG91 in a worker/notification service (not shown); dev logs it.
    log.info("otp_issued", phone=payload.phone, **({"otp_dev_only": otp} if settings.DEBUG else {}))
    return {"status": "otp_sent"}


@router.post("/otp/verify", response_model=TokenPair)
async def otp_verify(payload: OtpVerify, app_context: str = "customer", db: AsyncSession = Depends(get_db_txn)):
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
    if row.attempts >= settings.OTP_MAX_ATTEMPTS:
        raise HTTPException(http.HTTP_400_BAD_REQUEST, "Too many attempts. Request a new OTP.")

    if not verify_secret(payload.otp, row.otp_hash):
        row.attempts += 1
        raise HTTPException(http.HTTP_401_UNAUTHORIZED, "Incorrect OTP.")

    row.verified_at = now

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

    ctx = app_context if app_context in ("customer", "pujari", "admin") else "customer"
    access = create_access_token(subject=str(user.id), app_context=ctx)
    refresh = create_refresh_token(subject=str(user.id), app_context=ctx)
    db.add(
        AuthSession(
            id=uuid.uuid4(),
            user_id=user.id,
            device_id=None,
            app_context=ctx,
            refresh_token_hash=hash_secret(refresh),
            issued_at=now,
            expires_at=now + dt.timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
    )
    return TokenPair(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db_txn)):
    import jwt as _jwt

    try:
        claims = decode_token(payload.refresh_token)
    except _jwt.PyJWTError:
        raise HTTPException(http.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    if claims.get("type") != "refresh":
        raise HTTPException(http.HTTP_401_UNAUTHORIZED, "Not a refresh token")

    token_hash = hash_secret(payload.refresh_token)
    sess = (
        await db.execute(
            select(AuthSession).where(
                AuthSession.refresh_token_hash == token_hash,
                AuthSession.revoked_at.is_(None),
            ).with_for_update()
        )
    ).scalar_one_or_none()
    if sess is None:
        raise HTTPException(http.HTTP_401_UNAUTHORIZED, "Session revoked or unknown")

    now = dt.datetime.now(dt.UTC)
    sess.revoked_at = now
    sess.revoked_reason = "rotated"
    new_refresh = create_refresh_token(subject=claims["sub"], app_context=sess.app_context)
    db.add(
        AuthSession(
            id=uuid.uuid4(),
            user_id=sess.user_id,
            device_id=sess.device_id,
            app_context=sess.app_context,
            refresh_token_hash=hash_secret(new_refresh),
            issued_at=now,
            expires_at=now + dt.timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
    )
    access = create_access_token(subject=claims["sub"], app_context=sess.app_context)
    return TokenPair(access_token=access, refresh_token=new_refresh)


@router.post("/logout")
async def logout(payload: RefreshRequest, db: AsyncSession = Depends(get_db_txn)):
    token_hash = hash_secret(payload.refresh_token)
    await db.execute(
        text(
            "UPDATE auth_sessions SET revoked_at = now(), revoked_reason = 'logout' "
            "WHERE refresh_token_hash = :h AND revoked_at IS NULL"
        ),
        {"h": token_hash},
    )
    return {"status": "logged_out"}
