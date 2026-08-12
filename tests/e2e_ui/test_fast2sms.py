"""
TEST ONLY — direct FAST2SMS bulkV2 call for the E2E UI.

Never import from app/. Uses FAST2SMS_API_KEY from project .env.
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FAST2SMS_BULK_URL = "https://www.fast2sms.com/dev/bulkV2"


def _ten_digit(phone: str) -> str:
    digits = "".join(c for c in phone if c.isdigit())
    if digits.startswith("91") and len(digits) == 12:
        return digits[2:]
    return digits[-10:]


def send_direct_otp(phone: str) -> dict[str, Any]:
    """Call FAST2SMS bulkV2 directly. Returns JSON-serializable result for the UI."""
    load_dotenv(PROJECT_ROOT / ".env")
    key = os.environ.get("FAST2SMS_API_KEY", "").strip()
    if not key:
        return {"ok": False, "detail": "FAST2SMS_API_KEY missing in .env"}

    route = os.environ.get("FAST2SMS_OTP_ROUTE", "otp")
    mobile = _ten_digit(phone.strip())
    if len(mobile) != 10:
        return {"ok": False, "detail": f"Invalid phone (need 10-digit Indian mobile): {phone!r}"}

    otp = f"{secrets.randbelow(10**6):06d}"
    payload = {"route": route, "variables_values": otp, "numbers": mobile}
    headers = {"authorization": key}

    with httpx.Client(timeout=25.0) as client:
        res = client.post(FAST2SMS_BULK_URL, data=payload, headers=headers)

    try:
        body = res.json()
    except Exception:
        return {
            "ok": False,
            "detail": f"FAST2SMS returned non-JSON (HTTP {res.status_code})",
            "raw": res.text[:500],
        }

    accepted = res.status_code == 200 and body.get("return") is True
    status_code = body.get("status_code") if isinstance(body, dict) else None
    message = body.get("message") if isinstance(body, dict) else None
    hint = None
    if status_code == 996:
        hint = "FAST2SMS error 996: complete OTP KYC under Smart OTP (left menu) — add ₹100 wallet + Aadhaar verify + website URL."
    elif status_code == 999:
        hint = "FAST2SMS: add minimum ₹100 to wallet before using Dev API."
    elif status_code == 416:
        hint = "FAST2SMS: insufficient wallet balance."
    elif status_code == 412:
        hint = "FAST2SMS: invalid API key — copy from Dev API section."
    return {
        "ok": accepted,
        "http_status": res.status_code,
        "status_code": status_code,
        "return": body.get("return") if isinstance(body, dict) else None,
        "request_id": body.get("request_id") if isinstance(body, dict) else None,
        "message": message,
        "hint": hint,
        "otp": otp if accepted else None,
        "route": route,
        "numbers": mobile,
        "provider": "fast2sms",
    }
