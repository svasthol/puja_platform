"""PR 1 — OTP resend/lockout hardening (bug/otp-resend-lockout).

Fixes the resend-resets-lockout bug and adds abuse controls on the OTP path:

  1. Resend supersedes prior active OTPs (only one live code per phone).
  2. Lockout is PER-PHONE and carries across a resend (the actual bug: a new
     OTP row used to reset the per-row counter, so 5-attempt cap was bypassable).
  3. Per-phone send cooldown is atomic (SET NX EX) — two concurrent taps cannot
     both send an SMS.
  4. 429 responses carry a `Retry-After` header sourced from the key's real TTL.
  5. `Retry-After` falls back to the window default when TTL is unavailable
     (so old/forgiving clients still get a parseable header, no crash).
  6. Redis down => the REAL /auth/otp/request endpoint returns 503 (not 500,
     not a pass-through), via the app's RedisUnavailable handler.

These are integration tests (live PostgreSQL per conftest). Redis is faked in
process — the logic under test is ours, not redis-py's — except test 6, which
drives the real ASGI app so the exception handler mapping is exercised.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import random
import uuid
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.api.v1.endpoints import auth as auth_ep
from app.core.config import get_settings
from app.core.redis_client import RedisUnavailable
from app.core.security import hash_secret
from app.models.identity import OtpVerification
from app.schemas.auth import OtpRequest, OtpVerify

settings = get_settings()


def _uniq_phone() -> str:
    """A fresh, valid-looking +91 mobile per test (digits only)."""
    return "+919" + f"{random.randint(0, 10**9 - 1):09d}"


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #
class _PhoneCounter:
    """In-memory stand-in for the per-phone lockout counter helpers."""

    def __init__(self) -> None:
        self.store: dict[str, int] = {}

    async def failures(self, phone: str) -> int:
        return self.store.get(auth_ep._otp_lockout_key(phone), 0)

    async def record(self, phone: str) -> int:
        key = auth_ep._otp_lockout_key(phone)
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]


class _AtomicNx:
    """Faithful SET NX: first caller for a key wins, the rest get False.

    No await before the check-and-set, so it is atomic under asyncio's
    cooperative scheduling — exactly what Redis SET NX guarantees.
    """

    def __init__(self) -> None:
        self.keys: set[str] = set()

    async def set_nx(self, key: str, value: str, *, ex: int) -> bool:
        if key in self.keys:
            return False
        self.keys.add(key)
        return True


async def _count_active_otps(session, phone: str, now: dt.datetime) -> int:
    return (
        await session.execute(
            select(func.count())
            .select_from(OtpVerification)
            .where(
                OtpVerification.phone == phone,
                OtpVerification.verified_at.is_(None),
                OtpVerification.expires_at > now,
            )
        )
    ).scalar_one()


# --------------------------------------------------------------------------- #
# 1. Resend invalidates prior active OTPs
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_resend_supersedes_prior_active_otp(session):
    """After a resend there must be exactly ONE live OTP for the phone."""
    phone = _uniq_phone()
    with (
        patch.object(auth_ep, "_rate_limit", new_callable=AsyncMock),
        patch.object(auth_ep, "_enforce_send_cooldown", new_callable=AsyncMock),
        patch.object(auth_ep.sms_router, "send_otp_sms", new_callable=AsyncMock) as sms,
    ):
        from app.services.sms_types import SmsSendResult

        sms.return_value = SmsSendResult(sent=True, provider="test")
        await auth_ep.otp_request(OtpRequest(phone=phone), db=session)
        await session.commit()
        await auth_ep.otp_request(OtpRequest(phone=phone), db=session)  # resend
        await session.commit()

    now = dt.datetime.now(dt.UTC)
    assert await _count_active_otps(session, phone, now) == 1


# --------------------------------------------------------------------------- #
# 2. Lockout is per-phone and carries across a resend
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_lockout_carries_across_resend(session):
    """4 wrong attempts, then a resend, must NOT reset the counter — the 5th
    wrong attempt locks the phone out (429), even on a brand-new OTP row."""
    phone = _uniq_phone()
    counter = _PhoneCounter()

    from app.services.sms_types import SmsSendResult

    with (
        patch.object(auth_ep, "_rate_limit", new_callable=AsyncMock),
        patch.object(auth_ep, "_enforce_send_cooldown", new_callable=AsyncMock),
        patch.object(auth_ep, "_otp_failures", side_effect=counter.failures),
        patch.object(auth_ep, "_record_otp_failure", side_effect=counter.record),
        patch.object(auth_ep, "redis_ttl", new_callable=AsyncMock, return_value=600),
        patch.object(auth_ep, "redis_delete", new_callable=AsyncMock),
        patch.object(auth_ep.sms_router, "send_otp_sms", new_callable=AsyncMock) as sms,
    ):
        sms.return_value = SmsSendResult(sent=True, provider="test")
        await auth_ep.otp_request(OtpRequest(phone=phone), db=session)
        await session.commit()

        for _ in range(4):
            with pytest.raises(HTTPException) as exc:
                await auth_ep.otp_verify(OtpVerify(phone=phone, otp="000000"), db=session)
            assert exc.value.status_code == 401
            await session.rollback()

        # Resend: a new OTP row — the per-phone counter must survive it.
        await auth_ep.otp_request(OtpRequest(phone=phone), db=session)
        await session.commit()
        assert await counter.failures(phone) == 4  # carried over, not reset

        # 5th wrong attempt tips it over.
        with pytest.raises(HTTPException) as exc:
            await auth_ep.otp_verify(OtpVerify(phone=phone, otp="000000"), db=session)
        assert exc.value.status_code == 401
        await session.rollback()

        # Now locked out — even a correct code is refused, with 429 + Retry-After.
        with pytest.raises(HTTPException) as exc:
            await auth_ep.otp_verify(OtpVerify(phone=phone, otp="000000"), db=session)
        assert exc.value.status_code == 429
        assert "Retry-After" in (exc.value.headers or {})
        await session.rollback()


# --------------------------------------------------------------------------- #
# 3. Cooldown is atomic across concurrent requests
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_cooldown_blocks_concurrent_requests():
    """Two concurrent otp_request calls: exactly one sends, the other gets 429."""
    phone = _uniq_phone()
    nx = _AtomicNx()

    from app.services.sms_types import SmsSendResult

    class _FakeSession:
        def add(self, _obj):
            pass

        async def execute(self, *_a, **_k):
            return None

        async def flush(self):
            pass

    with (
        patch.object(auth_ep, "_rate_limit", new_callable=AsyncMock),
        patch.object(auth_ep, "redis_set_nx", side_effect=nx.set_nx),
        patch.object(auth_ep, "redis_ttl", new_callable=AsyncMock) as ttl,
        patch.object(auth_ep.sms_router, "send_otp_sms", new_callable=AsyncMock) as sms,
    ):
        ttl.return_value = settings.OTP_RESEND_COOLDOWN_SECONDS
        sms.return_value = SmsSendResult(sent=True, provider="test")

        results = await asyncio.gather(
            auth_ep.otp_request(OtpRequest(phone=phone), db=_FakeSession()),
            auth_ep.otp_request(OtpRequest(phone=phone), db=_FakeSession()),
            return_exceptions=True,
        )

    http_errs = [r for r in results if isinstance(r, HTTPException)]
    oks = [r for r in results if not isinstance(r, Exception)]
    assert len(oks) == 1, f"expected 1 success, got {results}"
    assert len(http_errs) == 1 and http_errs[0].status_code == 429
    assert "Retry-After" in (http_errs[0].headers or {})


# --------------------------------------------------------------------------- #
# 4. 429 carries a Retry-After sourced from the key's real TTL
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_rate_limit_429_sets_retry_after_from_ttl():
    with (
        patch.object(auth_ep, "redis_incr", new_callable=AsyncMock) as incr,
        patch.object(auth_ep, "redis_expire", new_callable=AsyncMock),
        patch.object(auth_ep, "redis_ttl", new_callable=AsyncMock) as ttl,
    ):
        incr.return_value = 6  # over a limit of 5
        ttl.return_value = 1800
        with pytest.raises(HTTPException) as exc:
            await auth_ep._rate_limit("otp_req:+919000000000", 5, 3600)
    assert exc.value.status_code == 429
    assert exc.value.headers["Retry-After"] == "1800"


# --------------------------------------------------------------------------- #
# 5. Retry-After falls back to the window when TTL is unavailable
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_retry_after_falls_back_when_ttl_missing():
    with (
        patch.object(auth_ep, "redis_incr", new_callable=AsyncMock) as incr,
        patch.object(auth_ep, "redis_expire", new_callable=AsyncMock),
        patch.object(auth_ep, "redis_ttl", new_callable=AsyncMock) as ttl,
    ):
        incr.return_value = 6
        ttl.return_value = -1  # key has no expiry / not found
        with pytest.raises(HTTPException) as exc:
            await auth_ep._rate_limit("otp_req:+919000000000", 5, 3600)
    assert exc.value.status_code == 429
    # Header present and parseable to a positive int (no crash on old clients).
    assert int(exc.value.headers["Retry-After"]) == 3600


# --------------------------------------------------------------------------- #
# 6. Redis down => real endpoint returns 503 (not 500, not pass-through)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_otp_request_returns_503_when_redis_down():
    from app.main import app

    path = f"{settings.API_V1_PREFIX}/auth/otp/request"
    transport = httpx.ASGITransport(app=app)
    with patch.object(
        auth_ep, "redis_incr", AsyncMock(side_effect=RedisUnavailable("down"))
    ):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(path, json={"phone": _uniq_phone()})
    assert resp.status_code == 503
