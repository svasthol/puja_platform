"""Phase 2 auth tests — SMS router wiring on otp/request."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.api.v1.endpoints.auth import otp_request
from app.schemas.auth import OtpRequest
from app.services.sms_types import SmsSendResult


class _FakeSession:
    def add(self, _obj):
        pass


@pytest.mark.asyncio
async def test_otp_request_logs_dev_otp_when_sms_not_sent():
    db = _FakeSession()
    with (
        patch("app.api.v1.endpoints.auth._rate_limit", new_callable=AsyncMock),
        patch(
            "app.api.v1.endpoints.auth.sms_router.send_otp_sms",
            new_callable=AsyncMock,
        ) as mock_sms,
        patch("app.api.v1.endpoints.auth.settings") as mock_settings,
    ):
        mock_settings.DEBUG = True
        mock_settings.OTP_EXPIRE_MINUTES = 10
        mock_sms.return_value = SmsSendResult(sent=False, error="all_failed")
        resp = await otp_request(OtpRequest(phone="+919999999999"), db=db)  # type: ignore[arg-type]
    assert resp["status"] == "otp_sent"
    assert resp["sms_sent"] is False


@pytest.mark.asyncio
async def test_otp_request_reports_sms_sent_with_provider():
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
        mock_sms.return_value = SmsSendResult(sent=True, provider="fast2sms")
        resp = await otp_request(OtpRequest(phone="+919876543210"), db=db)  # type: ignore[arg-type]
    assert resp["sms_sent"] is True
    assert resp["sms_provider"] == "fast2sms"
    mock_sms.assert_awaited_once()
