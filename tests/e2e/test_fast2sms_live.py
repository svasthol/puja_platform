"""
Live FAST2SMS integration tests — tests/e2e only (no app/ edits).

Validates your FAST2SMS_API_KEY from .env. Two modes:

1. **direct** — calls FAST2SMS bulkV2 API (no uvicorn required)
2. **api**    — POST /v1/auth/otp/request on running API (full stack)

Run:

    # Direct vendor check (fastest — confirms API key + credits):
    set OTP_TEST_PHONE=+919876543210
    pytest tests/e2e/test_fast2sms_live.py -q -k direct

    # Full stack (uvicorn must be running on :8000):
    uvicorn app.main:app --reload --port 8000
    set OTP_TEST_PHONE=+919876543210
    set OTP_REQUIRE_FAST2SMS=1
    pytest tests/e2e/test_fast2sms_live.py -q -k api

    # CLI smoke (no pytest):
    python tests/e2e/fast2sms_smoke.py direct --phone +919876543210
    python tests/e2e/fast2sms_smoke.py api --phone +919876543210

Env:
    FAST2SMS_API_KEY     from .env (required)
    OTP_TEST_PHONE       your real 10-digit Indian mobile (+91...)
    OTP_REQUIRE_FAST2SMS if 1, api test fails when sms_sent=false
    E2E_API_UPSTREAM     default http://127.0.0.1:8000
"""
from __future__ import annotations

import os
import secrets
import uuid
from pathlib import Path

import httpx
import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

API_BASE = os.environ.get("E2E_API_UPSTREAM", "http://127.0.0.1:8000").rstrip("/")
OTP_PHONE = os.environ.get("OTP_TEST_PHONE", "").strip()
REQUIRE_FAST2SMS = os.environ.get("OTP_REQUIRE_FAST2SMS", "").lower() in ("1", "true", "yes")
FAST2SMS_KEY = os.environ.get("FAST2SMS_API_KEY", "").strip()
FAST2SMS_OTP_ROUTE = os.environ.get("FAST2SMS_OTP_ROUTE", "otp")
FAST2SMS_BULK_URL = "https://www.fast2sms.com/dev/bulkV2"


def _real_phone_required() -> str:
    if not OTP_PHONE or OTP_PHONE in ("+919999999999", "+910000000000"):
        pytest.skip("Set OTP_TEST_PHONE to your real mobile (+91XXXXXXXXXX) for live SMS test")
    return OTP_PHONE


def _fast2sms_key_required() -> str:
    if not FAST2SMS_KEY:
        pytest.skip("FAST2SMS_API_KEY missing in .env")
    return FAST2SMS_KEY


def _ten_digit(phone: str) -> str:
    digits = "".join(c for c in phone if c.isdigit())
    if digits.startswith("91") and len(digits) == 12:
        return digits[2:]
    return digits[-10:]


@pytest.fixture(scope="module")
def api_up():
    try:
        with httpx.Client(timeout=3.0) as client:
            res = client.get(f"{API_BASE}/health")
        if res.status_code != 200:
            pytest.skip(f"API unhealthy at {API_BASE}/health → {res.status_code}")
    except httpx.HTTPError as exc:
        pytest.skip(f"API not reachable at {API_BASE}: {exc}")


class TestFast2SmsDirect:
    """Hit FAST2SMS vendor API directly — confirms API key without uvicorn."""

    def test_fast2sms_direct_otp_send(self):
        _fast2sms_key_required()
        phone = _real_phone_required()
        mobile = _ten_digit(phone)
        otp = f"{secrets.randbelow(10**6):06d}"
        payload = {
            "route": FAST2SMS_OTP_ROUTE,
            "variables_values": otp,
            "numbers": mobile,
        }
        headers = {"authorization": FAST2SMS_KEY}
        with httpx.Client(timeout=20.0) as client:
            res = client.post(FAST2SMS_BULK_URL, data=payload, headers=headers)
        assert res.status_code == 200, res.text
        body = res.json()
        assert body.get("return") is True, (
            f"FAST2SMS rejected request: {body}. "
            "Check dashboard credits, route=otp, and API key (Dev API section)."
        )
        assert body.get("request_id"), f"Expected request_id in response: {body}"
        print(f"\nFAST2SMS direct OK — request_id={body.get('request_id')} otp={otp} phone={mobile}")


class TestFast2SmsViaApi:
    """Full stack: uvicorn → sms_router → FAST2SMS."""

    def test_otp_request_accepts_and_reports_sms_fields(self, api_up):
        phone = f"+91{uuid.uuid4().int % 10_000_000_000:010d}"
        with httpx.Client(timeout=20.0) as client:
            res = client.post(f"{API_BASE}/v1/auth/otp/request", json={"phone": phone})
        assert res.status_code == 202, res.text
        body = res.json()
        assert body.get("status") == "otp_sent"
        assert "sms_sent" in body
        assert "sms_provider" in body

    @pytest.mark.skipif(not REQUIRE_FAST2SMS, reason="Set OTP_REQUIRE_FAST2SMS=1 to assert real SMS send")
    def test_otp_request_fast2sms_sms_sent(self, api_up):
        _fast2sms_key_required()
        phone = _real_phone_required()
        with httpx.Client(timeout=25.0) as client:
            res = client.post(f"{API_BASE}/v1/auth/otp/request", json={"phone": phone})
        assert res.status_code == 202, res.text
        body = res.json()
        assert body.get("sms_sent") is True, (
            f"sms_sent=false (provider={body.get('sms_provider')}). "
            "Check .env: FAST2SMS_API_KEY, SMS_PROVIDER_ORDER=fast2sms, MSG91_ENABLED=false. "
            "See uvicorn logs for fast2sms_sent or fast2sms_rejected."
        )
        assert body.get("sms_provider") == "fast2sms", (
            f"Expected fast2sms, got {body.get('sms_provider')}. "
            "Ensure SMS_PROVIDER_ORDER starts with fast2sms and MSG91_ENABLED=false."
        )
        print(f"\nAPI OTP OK — sms_provider=fast2sms phone={phone[-4:].rjust(len(phone), '*')}")
