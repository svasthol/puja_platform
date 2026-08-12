"""Sprint 4-0 auth tests — P-ADMIN-AUTH-FIX + P-AUTH-FIX.

Covers the three bugs the auth review found:
  1. app_context query-param escalation  -> body field, 'admin' impossible (422)
  2. refresh/logout bcrypt-equality lookup -> jti lookup + verify_secret,
     rotation, reuse-detection (revoke-all), idempotent logout
  3. OTP lockout dead code (rollback ate the increment) -> Redis counter

DB tests run against live PostgreSQL (conftest DATABASE_URL) with migration 009
applied. Redis is faked in-process — the lockout logic under test is ours, not
redis-py's.
"""
from __future__ import annotations

import datetime as dt
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, text

from app.api.v1.endpoints import auth as auth_ep
from app.core.security import decode_token, hash_secret
from app.models.identity import AuthSession, OtpVerification
from app.schemas.auth import OtpVerify, RefreshRequest


# --------------------------------------------------------------------------- #
# 1. P-ADMIN-AUTH-FIX — schema-level guarantees
# --------------------------------------------------------------------------- #
def test_otp_verify_rejects_admin_context():
    """'admin' must be impossible on the SMS OTP path — 422 before handler code."""
    with pytest.raises(ValidationError):
        OtpVerify(phone="+919876543210", otp="123456", app_context="admin")


def test_otp_verify_accepts_customer_and_pujari():
    assert OtpVerify(phone="+919876543210", otp="123456").app_context == "customer"
    assert (
        OtpVerify(phone="+919876543210", otp="123456", app_context="pujari").app_context
        == "pujari"
    )


def test_otp_verify_has_no_query_parameters():
    """The escalation vector was a bare scalar default -> FastAPI query param.
    Guard against regression: otp_verify must declare no query parameters."""
    import inspect

    sig = inspect.signature(auth_ep.otp_verify)
    assert set(sig.parameters) == {"payload", "db"}


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
async def _mk_user(session, phone: str) -> uuid.UUID:
    uid = uuid.uuid4()
    await session.execute(
        text("INSERT INTO users (id, full_name, phone) VALUES (:id, 'T', :ph)"),
        {"id": str(uid), "ph": phone},
    )
    return uid


async def _issue(session, user_id: uuid.UUID, ctx: str = "customer"):
    pair = auth_ep._issue_token_pair(
        session,
        user_id=user_id,
        app_context=ctx,
        device_id=None,
        now=dt.datetime.now(dt.UTC),
    )
    await session.commit()
    return pair


def _uniq_phone() -> str:
    return "+91977" + uuid.uuid4().hex[:7]


# --------------------------------------------------------------------------- #
# 2. P-AUTH-FIX — refresh / logout on live DB
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_issued_session_stores_jti(session):
    """The session row must carry the token's jti — the lookup key."""
    uid = await _mk_user(session, _uniq_phone())
    pair = await _issue(session, uid)
    jti = decode_token(pair.refresh_token)["jti"]
    sess = (
        await session.execute(select(AuthSession).where(AuthSession.refresh_jti == jti))
    ).scalar_one()
    assert sess.user_id == uid
    assert sess.revoked_at is None


@pytest.mark.asyncio
async def test_refresh_rotates_session(session):
    """Valid refresh -> new pair; old session revoked 'rotated'; new session live."""
    uid = await _mk_user(session, _uniq_phone())
    pair = await _issue(session, uid)
    old_jti = decode_token(pair.refresh_token)["jti"]

    new_pair = await auth_ep.refresh(RefreshRequest(refresh_token=pair.refresh_token), db=session)
    await session.commit()

    assert new_pair.access_token and new_pair.refresh_token != pair.refresh_token
    old = (
        await session.execute(select(AuthSession).where(AuthSession.refresh_jti == old_jti))
    ).scalar_one()
    assert old.revoked_reason == "rotated"
    new_jti = decode_token(new_pair.refresh_token)["jti"]
    new = (
        await session.execute(select(AuthSession).where(AuthSession.refresh_jti == new_jti))
    ).scalar_one()
    assert new.revoked_at is None and new.app_context == "customer"


@pytest.mark.asyncio
async def test_refresh_reuse_revokes_every_live_session(session):
    """Replaying a rotated token = theft signal -> all live sessions die."""
    uid = await _mk_user(session, _uniq_phone())
    pair = await _issue(session, uid)
    await auth_ep.refresh(RefreshRequest(refresh_token=pair.refresh_token), db=session)
    await session.commit()

    with pytest.raises(HTTPException) as exc:
        await auth_ep.refresh(RefreshRequest(refresh_token=pair.refresh_token), db=session)
    assert exc.value.status_code == 401
    await session.commit()

    live = (
        await session.execute(
            select(AuthSession).where(
                AuthSession.user_id == uid, AuthSession.revoked_at.is_(None)
            )
        )
    ).scalars().all()
    assert live == []
    reasons = {
        s.revoked_reason
        for s in (
            await session.execute(select(AuthSession).where(AuthSession.user_id == uid))
        ).scalars()
    }
    assert "refresh_reuse" in reasons


@pytest.mark.asyncio
async def test_refresh_rejects_forged_token_with_stolen_jti(session):
    """jti matches a session but token bytes differ -> hash verify fails -> 401."""
    import jwt as pyjwt

    from app.core.config import get_settings

    uid = await _mk_user(session, _uniq_phone())
    pair = await _issue(session, uid)
    claims = decode_token(pair.refresh_token)
    forged = pyjwt.encode(
        {**claims, "sub": str(uuid.uuid4())},  # same jti, different payload
        get_settings().SECRET_KEY,
        algorithm="HS256",
    )
    with pytest.raises(HTTPException) as exc:
        await auth_ep.refresh(RefreshRequest(refresh_token=forged), db=session)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_refresh_garbage_token_401(session):
    with pytest.raises(HTTPException) as exc:
        await auth_ep.refresh(RefreshRequest(refresh_token="not-a-jwt"), db=session)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_and_is_idempotent(session):
    uid = await _mk_user(session, _uniq_phone())
    pair = await _issue(session, uid)
    jti = decode_token(pair.refresh_token)["jti"]

    resp = await auth_ep.logout(RefreshRequest(refresh_token=pair.refresh_token), db=session)
    await session.commit()
    assert resp == {"status": "logged_out"}
    sess = (
        await session.execute(select(AuthSession).where(AuthSession.refresh_jti == jti))
    ).scalar_one()
    assert sess.revoked_reason == "logout"

    # Second logout with the same token: still 200, no error (idempotent).
    resp2 = await auth_ep.logout(RefreshRequest(refresh_token=pair.refresh_token), db=session)
    assert resp2 == {"status": "logged_out"}

    # A logged-out token must not refresh — and reuse-detection fires.
    with pytest.raises(HTTPException) as exc:
        await auth_ep.refresh(RefreshRequest(refresh_token=pair.refresh_token), db=session)
    assert exc.value.status_code == 401


# --------------------------------------------------------------------------- #
# 3. P-AUTH-FIX — OTP lockout survives the transaction rollback
# --------------------------------------------------------------------------- #
class _FakeRedisCounter:
    """In-memory stand-in for the auth module's Redis helpers."""

    def __init__(self):
        self.store: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

    async def expire(self, key: str, seconds: int) -> None:
        pass

    async def delete(self, key: str) -> int:
        return 1 if self.store.pop(key, None) is not None else 0

    async def get_int(self, key: str) -> int:
        return self.store.get(key, 0)


@pytest.mark.asyncio
async def test_otp_lockout_persists_across_rollbacks(session):
    """5 wrong OTPs -> locked, even though each 401 rolls the DB txn back.
    The correct OTP must ALSO be rejected once locked."""
    phone = _uniq_phone()
    now = dt.datetime.now(dt.UTC)
    otp_id = uuid.uuid4()
    session.add(
        OtpVerification(
            id=otp_id,
            user_id=None,
            phone=phone,
            otp_hash=hash_secret("111111"),
            purpose="login",
            attempts=0,
            expires_at=now + dt.timedelta(minutes=10),
            created_at=now,
        )
    )
    await session.commit()

    fake = _FakeRedisCounter()

    async def fake_failures(row_id):
        return await fake.get_int(f"otp_fail:{row_id}")

    async def fake_record(row_id):
        return await fake.incr(f"otp_fail:{row_id}")

    with (
        patch.object(auth_ep, "_rate_limit", new_callable=AsyncMock),
        patch.object(auth_ep, "_otp_failures", side_effect=fake_failures),
        patch.object(auth_ep, "_record_otp_failure", side_effect=fake_record),
        patch.object(auth_ep, "redis_delete", new_callable=AsyncMock),
    ):
        for _ in range(5):
            with pytest.raises(HTTPException) as exc:
                await auth_ep.otp_verify(
                    OtpVerify(phone=phone, otp="000000"), db=session
                )
            assert exc.value.status_code == 401
            await session.rollback()  # mirror get_db_txn behaviour on error

        # 6th wrong attempt: locked out (400, not 401).
        with pytest.raises(HTTPException) as exc:
            await auth_ep.otp_verify(OtpVerify(phone=phone, otp="000000"), db=session)
        assert exc.value.status_code == 400
        assert "Too many attempts" in exc.value.detail
        await session.rollback()

        # Even the CORRECT OTP is rejected once locked.
        with pytest.raises(HTTPException) as exc:
            await auth_ep.otp_verify(OtpVerify(phone=phone, otp="111111"), db=session)
        assert exc.value.status_code == 400
        await session.rollback()

    assert fake.store[f"otp_fail:{otp_id}"] == 5
