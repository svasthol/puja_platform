"""OTP verify resolves the same user regardless of +91 vs 10-digit input."""
from __future__ import annotations

import datetime as dt
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.api.v1.endpoints import auth as auth_ep
from app.core.security import hash_secret
from app.models.identity import OtpVerification, User
from app.schemas.auth import OtpRequest, OtpVerify


from app.services.sms_types import SmsSendResult


class _FakeSession:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)


@pytest.mark.asyncio
async def test_otp_request_stores_canonical_phone():
    db = _FakeSession()
    with (
        patch("app.api.v1.endpoints.auth._rate_limit", new_callable=AsyncMock),
        patch(
            "app.api.v1.endpoints.auth.sms_router.send_otp_sms",
            new_callable=AsyncMock,
        ) as mock_sms,
        patch("app.api.v1.endpoints.auth.settings") as mock_settings,
    ):
        mock_settings.DEBUG = False
        mock_settings.OTP_EXPIRE_MINUTES = 10
        mock_settings.OTP_RATE_LIMIT_PER_HOUR = 100
        mock_sms.return_value = SmsSendResult(sent=True, provider="test")
        await auth_ep.otp_request(OtpRequest(phone="9515165674"), db=db)  # type: ignore[arg-type]
    otp_row = next(o for o in db.added if isinstance(o, OtpVerification))
    assert otp_row.phone == "+919515165674"


@pytest.mark.asyncio
async def test_otp_verify_cross_format_matches_canonical_otp_row(session):
    """Request OTP with 10-digit; verify with +91 — same canonical key."""
    now = dt.datetime.now(dt.UTC)
    canonical = "+919876543210"
    session.add(
        OtpVerification(
            id=uuid.uuid4(),
            user_id=None,
            phone=canonical,
            otp_hash=hash_secret("654321"),
            purpose="login",
            attempts=0,
            expires_at=now + dt.timedelta(minutes=10),
            created_at=now,
        )
    )
    await session.commit()

    with (
        patch.object(auth_ep, "_rate_limit", new_callable=AsyncMock),
        patch.object(auth_ep, "_otp_failures", new_callable=AsyncMock, return_value=0),
        patch.object(auth_ep, "redis_delete", new_callable=AsyncMock),
    ):
        pair = await auth_ep.otp_verify(
            OtpVerify(phone="9876543210", otp="654321", app_context="customer"),
            db=session,
        )
    assert pair.access_token
    user = (
        await session.execute(select(User).where(User.phone == canonical))
    ).scalar_one_or_none()
    assert user is not None
