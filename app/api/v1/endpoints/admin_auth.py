"""Admin authentication (P-ADMIN-AUTH) — TOTP login, no SMS/DLT.

This endpoint is the ONLY issuance path for an app_context=admin token. The SMS
OTP path (auth.py) is Literal["customer","pujari"] and can never mint admin
(P-ADMIN-AUTH-FIX). Issuance gate (P-ADMIN-ROLE half 1): a token is minted only
when the user holds an admin/support role AND presents a valid TOTP code for an
activated credential.

Credentials are provisioned by an existing admin (admin.py) or the bootstrap
script — never self-service — so there is no enrolment race. To avoid account
enumeration, every failure returns the same generic 401.
"""
from __future__ import annotations

import datetime as dt

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status as http
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import _issue_token_pair, _rate_limit
from app.core.config import get_settings
from app.core.crypto import TotpKeyUnavailable, decrypt_secret
from app.core import totp
from app.core.dependencies import ADMIN_ROLES
from app.db.engine import get_db_txn
from app.models.admin import AdminCredential
from app.models.identity import User, UserRole
from app.models.lookups import Role
from app.schemas.admin_auth import AdminLoginRequest
from app.schemas.auth import TokenPair

router = APIRouter(prefix="/admin/auth", tags=["admin-auth"])
log = structlog.get_logger()
settings = get_settings()

_GENERIC_401 = "Invalid credentials."


@router.post("/login", response_model=TokenPair)
async def admin_login(
    payload: AdminLoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_txn),
):
    # Brute-force guard per phone — TOTP is only 6 digits.
    await _rate_limit(
        f"admin_login:{payload.phone}", settings.ADMIN_LOGIN_RATE_LIMIT_PER_HOUR, 3600
    )
    now = dt.datetime.now(dt.UTC)

    # Resolve user + roles + credential in one guarded read. FOR UPDATE on the
    # credential serialises concurrent logins so the replay check is race-free.
    user = (
        await db.execute(select(User).where(User.phone == payload.phone))
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(http.HTTP_401_UNAUTHORIZED, _GENERIC_401)

    roles = (
        await db.execute(
            select(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user.id)
        )
    ).scalars().all()
    if not any(r in ADMIN_ROLES for r in roles):
        log.warning("admin_login_denied", reason="no_role", user_id=str(user.id))
        raise HTTPException(http.HTTP_401_UNAUTHORIZED, _GENERIC_401)

    cred = (
        await db.execute(
            select(AdminCredential)
            .where(AdminCredential.user_id == user.id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if cred is None:
        log.warning("admin_login_denied", reason="no_credential", user_id=str(user.id))
        raise HTTPException(http.HTTP_401_UNAUTHORIZED, _GENERIC_401)

    try:
        secret = decrypt_secret(cred.totp_secret_enc)
    except TotpKeyUnavailable:
        # Misconfiguration (key rotated out) — 503, not 401: it is not the
        # user's fault and must page ops rather than look like a bad code.
        log.error("admin_login_totp_key_unavailable", user_id=str(user.id))
        raise HTTPException(http.HTTP_503_SERVICE_UNAVAILABLE, "Admin auth temporarily unavailable.")

    matched_step = totp.verify(
        secret,
        payload.code,
        step=settings.TOTP_STEP_SECONDS,
        window=settings.TOTP_VERIFY_WINDOW,
    )
    if matched_step is None:
        log.warning("admin_login_denied", reason="bad_code", user_id=str(user.id))
        raise HTTPException(http.HTTP_401_UNAUTHORIZED, _GENERIC_401)

    # Replay guard: a code (time-step) is accepted at most once.
    if matched_step <= cred.last_used_step:
        log.warning("admin_login_denied", reason="code_replay", user_id=str(user.id))
        raise HTTPException(http.HTTP_401_UNAUTHORIZED, _GENERIC_401)

    cred.last_used_step = matched_step
    cred.updated_at = now
    if cred.activated_at is None:
        cred.activated_at = now  # first successful login activates the credential

    log.info("admin_login_ok", user_id=str(user.id), roles=list(roles))
    return _issue_token_pair(
        db, user_id=user.id, app_context="admin", device_id=None, now=now
    )
