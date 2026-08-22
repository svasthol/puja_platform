"""
Live Setu DigiLocker KYC tests — tests/e2e only.

Run:

  # Direct Setu sandbox (no uvicorn):
  pytest tests/e2e/test_kyc_digilocker_live.py -q -k direct

  # Full stack (uvicorn on :8000, DEBUG=true):
  $env:KYC_TEST_PHONE="+917675834207"
  pytest tests/e2e/test_kyc_digilocker_live.py -q -k api_start

  # CLI:
  python tests/e2e/setu_digilocker_smoke.py direct
  python tests/e2e/setu_digilocker_smoke.py api --phone +917675834207
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import httpx
import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

API_BASE = os.environ.get("E2E_API_UPSTREAM", "http://127.0.0.1:8000").rstrip("/")
SETU_BASE = os.environ.get("KYC_SETU_BASE_URL", "https://dg-sandbox.setu.co").rstrip("/")


def _kyc_env_ready() -> None:
    missing = [
        k
        for k in (
            "KYC_REDIRECT_URL",
            "KYC_SETU_CLIENT_ID",
            "KYC_SETU_CLIENT_SECRET",
            "KYC_SETU_DIGILOCKER_PRODUCT_ID",
            "KYC_IDENTITY_PEPPER",
            "SECRET_KEY",
        )
        if not os.environ.get(k, "").strip()
    ]
    if missing:
        pytest.skip(f"Missing .env: {', '.join(missing)}")


def _setu_headers() -> dict[str, str]:
    return {
        "x-client-id": os.environ["KYC_SETU_CLIENT_ID"],
        "x-client-secret": os.environ["KYC_SETU_CLIENT_SECRET"],
        "x-product-instance-id": os.environ["KYC_SETU_DIGILOCKER_PRODUCT_ID"],
        "Content-Type": "application/json",
    }


@pytest.fixture(scope="module")
def api_up():
    root = API_BASE.replace("/v1", "").rstrip("/")
    try:
        with httpx.Client(timeout=3.0) as client:
            res = client.get(f"{root}/health")
        if res.status_code != 200:
            pytest.skip(f"API unhealthy at {root}/health → {res.status_code}")
    except httpx.HTTPError as exc:
        pytest.skip(f"API not reachable at {API_BASE}: {exc}")


class TestSetuDirect:
    def test_setu_sandbox_start_digilocker(self):
        _kyc_env_ready()
        redirect = os.environ["KYC_REDIRECT_URL"].strip()
        with httpx.Client(timeout=25.0) as client:
            res = client.post(
                f"{SETU_BASE}/api/digilocker",
                headers=_setu_headers(),
                json={"redirectUrl": redirect},
            )
        assert res.status_code in (200, 201), res.text
        body = res.json()
        assert body.get("id"), f"Expected Setu request id: {body}"
        assert body.get("url"), f"Expected DigiLocker url: {body}"
        print(f"\nSetu direct OK — id={body['id']}")


class TestKycViaApi:
    def test_start_digilocker_returns_url(self, api_up):
        _kyc_env_ready()
        phone = f"+91{uuid.uuid4().int % 10_000_000_000:010d}"
        with httpx.Client(timeout=30.0) as client:
            otp_req = client.post(f"{API_BASE}/v1/auth/otp/request", json={"phone": phone})
            assert otp_req.status_code == 202, otp_req.text
            otp_body = otp_req.json()
            otp = otp_body.get("otp_dev_only")
            if not otp:
                pytest.skip("Set DEBUG=true for otp_dev_only or use setu_digilocker_smoke.py api")
            verify = client.post(
                f"{API_BASE}/v1/auth/otp/verify",
                json={"phone": phone, "otp": str(otp), "app_context": "pujari"},
            )
            assert verify.status_code == 200, verify.text
            token = verify.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            client.post(
                f"{API_BASE}/v1/pujari/register",
                headers=headers,
                json={"bio": "pytest kyc", "years_experience": 1},
            )
            start = client.post(f"{API_BASE}/v1/pujari/kyc/digilocker", headers=headers)
        assert start.status_code == 200, start.text
        body = start.json()
        assert body.get("request_id")
        assert body.get("url")
        assert "digilocker" in body["url"].lower() or "setu" in body["url"].lower()
        print(f"\nAPI start OK — request_id={body['request_id']}")
