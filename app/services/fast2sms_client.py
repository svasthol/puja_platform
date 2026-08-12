"""
FAST2SMS client — OTP + Quick SMS (no DLT header required on Quick route).

Dev API docs: https://docs.fast2sms.com/
  - OTP:  POST /dev/bulkV2  route=otp, variables_values=<otp>, numbers=<10-digit>
  - Text: POST /dev/bulkV2  route=q, message=<text>, numbers=<10-digit>  (Quick SMS)
"""
from __future__ import annotations

import httpx
import structlog

from app.core.config import get_settings
from app.services.sms_phone import normalize_india_mobile_ten

log = structlog.get_logger()
settings = get_settings()

_BULK_URL = "https://www.fast2sms.com/dev/bulkV2"
_TIMEOUT = httpx.Timeout(connect=3.0, read=8.0, write=3.0, pool=3.0)


def _headers() -> dict[str, str]:
    return {"authorization": settings.FAST2SMS_API_KEY}


def _masked(phone: str) -> str:
    return phone[-4:].rjust(len(phone), "*")


def _accepted(resp: httpx.Response, *, phone: str, kind: str) -> bool:
    resp.raise_for_status()
    try:
        data = resp.json()
    except ValueError:
        log.error("fast2sms_bad_response", kind=kind, phone=_masked(phone), body=resp.text[:300])
        return False
    if isinstance(data, dict) and data.get("return") is True:
        log.info(
            "fast2sms_sent",
            kind=kind,
            phone=_masked(phone),
            request_id=data.get("request_id"),
        )
        return True
    err = data.get("message") if isinstance(data, dict) else data
    log.error("fast2sms_rejected", kind=kind, phone=_masked(phone), error=str(err)[:300])
    return False


def _configured() -> bool:
    return bool(settings.FAST2SMS_API_KEY)


def send_otp_sms_sync(phone: str, otp: str) -> bool:
    if not _configured():
        return False
    mobile = normalize_india_mobile_ten(phone)
    payload = {
        "route": settings.FAST2SMS_OTP_ROUTE,
        "variables_values": otp,
        "numbers": mobile,
    }
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.post(_BULK_URL, data=payload, headers=_headers())
        return _accepted(resp, phone=mobile, kind="otp")
    except httpx.HTTPError as exc:
        log.error("fast2sms_otp_failed", phone=_masked(mobile), error=str(exc))
        return False


def send_transactional_sms_sync(phone: str, message: str) -> bool:
    """Quick SMS route — no DLT template; random sender id per FAST2SMS docs."""
    if not _configured():
        return False
    mobile = normalize_india_mobile_ten(phone)
    payload = {
        "route": settings.FAST2SMS_QUICK_ROUTE,
        "message": message[:160],
        "language": "english",
        "numbers": mobile,
    }
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.post(_BULK_URL, data=payload, headers=_headers())
        return _accepted(resp, phone=mobile, kind="txn")
    except httpx.HTTPError as exc:
        log.error("fast2sms_txn_failed", phone=_masked(mobile), error=str(exc))
        return False
