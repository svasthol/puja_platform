"""Reusable QA API client: dev OTP login for customer/pujari, token helpers."""
from __future__ import annotations

import httpx

BASE = "http://127.0.0.1:8000"


def login(phone: str, app_context: str = "customer", timeout: float = 20.0) -> str:
    """Dev OTP login -> access token. Relies on DEBUG otp_dev_only in response."""
    with httpx.Client(base_url=BASE, timeout=timeout) as c:
        r = c.post("/v1/auth/otp/request", json={"phone": phone})
        r.raise_for_status()
        body = r.json()
        otp = body.get("otp_dev_only")
        if not otp:
            raise RuntimeError(f"no otp_dev_only in response: {body}")
        v = c.post(
            "/v1/auth/otp/verify",
            json={"phone": phone, "otp": otp, "app_context": app_context},
        )
        v.raise_for_status()
        tok = v.json()
        return tok["access_token"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
