"""
Live OTP / MSG91 integration tests — tests/ only, no app imports.

Hits a **running** API (same path as E2E UI: serve.py proxy → uvicorn :8000).
Skipped automatically when the API is unreachable.

Run (API must be up: uvicorn app.main:app --port 8000):

    # Dev mode — request only (sms_sent false, use uvicorn otp_dev_only for verify)
    pytest tests/test_otp_live_integration.py -q

    # After copying OTP from uvicorn log (DEBUG=true):
    set OTP_TEST_OTP=123456
    pytest tests/test_otp_live_integration.py -q -k verify

    # Require real MSG91 send (keys in .env):
    set OTP_REQUIRE_MSG91=1
    pytest tests/test_otp_live_integration.py -q -k msg91

Env:
    E2E_API_UPSTREAM   default http://127.0.0.1:8000
    OTP_TEST_PHONE     default +919999999999 (use your real phone for MSG91 SMS)
    OTP_TEST_OTP       6-digit code for verify test (manual / from SMS or log)
    OTP_REQUIRE_MSG91  if 1, fail when MSG91 keys set but sms_sent is false
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import httpx
import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

API_BASE = os.environ.get("E2E_API_UPSTREAM", "http://127.0.0.1:8000").rstrip("/")
OTP_PHONE = os.environ.get("OTP_TEST_PHONE", "+919999999999")
OTP_CODE = os.environ.get("OTP_TEST_OTP", "")
REQUIRE_MSG91 = os.environ.get("OTP_REQUIRE_MSG91", "").lower() in ("1", "true", "yes")
MSG91_CONFIGURED = bool(os.environ.get("MSG91_AUTH_KEY") and os.environ.get("MSG91_TEMPLATE_ID"))


@pytest.fixture(scope="module")
def api_up():
    """Skip module when uvicorn is not running."""
    try:
        with httpx.Client(timeout=3.0) as client:
            res = client.get(f"{API_BASE}/health")
        if res.status_code != 200:
            pytest.skip(f"API unhealthy at {API_BASE}/health → {res.status_code}")
    except httpx.HTTPError as exc:
        pytest.skip(f"API not reachable at {API_BASE}: {exc}")


def test_otp_request_returns_accepted(api_up):
    """POST /v1/auth/otp/request → 202 + otp_sent (E2E customer/partner step 1)."""
    phone = f"+91{uuid.uuid4().int % 10_000_000_000:010d}"  # unique per run → no rate-limit clash
    with httpx.Client(timeout=15.0) as client:
        res = client.post(f"{API_BASE}/v1/auth/otp/request", json={"phone": phone})
    assert res.status_code == 202, res.text
    body = res.json()
    assert body.get("status") == "otp_sent"
    assert "sms_sent" in body


@pytest.mark.skipif(not REQUIRE_MSG91, reason="Set OTP_REQUIRE_MSG91=1 to assert real MSG91 send")
def test_otp_request_msg91_sms_sent(api_up):
    """When MSG91 keys are in .env, sms_sent must be true (confirms integration)."""
    if not MSG91_CONFIGURED:
        pytest.skip("MSG91_AUTH_KEY or MSG91_TEMPLATE_ID missing in .env")
    phone = os.environ.get("OTP_TEST_PHONE", "").strip()
    if not phone or phone == "+919999999999":
        pytest.skip("Set OTP_TEST_PHONE to your real mobile for MSG91 SMS test")
    with httpx.Client(timeout=20.0) as client:
        res = client.post(f"{API_BASE}/v1/auth/otp/request", json={"phone": phone})
    assert res.status_code == 202, res.text
    body = res.json()
    assert body.get("sms_sent") is True, (
        "MSG91 keys configured but sms_sent=false — check template ID, auth key, "
        "and MSG91 dashboard (template approved, test credits)."
    )


@pytest.mark.skipif(not OTP_CODE, reason="Set OTP_TEST_OTP=XXXXXX after otp/request (SMS or uvicorn otp_dev_only)")
def test_otp_verify_issues_tokens(api_up):
    """Verify step only — run otp/request first (E2E UI or otp_smoke.py request)."""
    phone = OTP_PHONE
    with httpx.Client(timeout=15.0) as client:
        ver = client.post(
            f"{API_BASE}/v1/auth/otp/verify",
            json={"phone": phone, "otp": OTP_CODE, "app_context": "customer"},
        )
    assert ver.status_code == 200, ver.text
    data = ver.json()
    assert data.get("access_token")
    assert data.get("refresh_token")
