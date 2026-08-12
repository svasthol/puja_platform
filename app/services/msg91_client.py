"""
MSG91 SMS client — OTP (P-AUTH) and transactional fallback (P-NOTIFY).

When MSG91_AUTH_KEY is empty the caller must fall back to dev logging (DEBUG OTP).
Never logs raw OTP in production.
"""
from __future__ import annotations

import re

import httpx
import structlog

from app.core.config import get_settings
from app.services.sms_phone import normalize_india_mobile_e164

log = structlog.get_logger()
settings = get_settings()

_MSG91_OTP_URL = "https://control.msg91.com/api/v5/otp"
_MSG91_FLOW_URL = "https://control.msg91.com/api/v5/flow"
_TIMEOUT = httpx.Timeout(connect=3.0, read=8.0, write=3.0, pool=3.0)


def normalize_india_mobile(phone: str) -> str:
    """Backward-compatible alias (MSG91 E.164 without '+')."""
    return normalize_india_mobile_e164(phone)


def _headers() -> dict[str, str]:
    return {"authkey": settings.MSG91_AUTH_KEY, "Content-Type": "application/json"}


def _masked_phone(mobile: str) -> str:
    return mobile[-4:].rjust(len(mobile), "*")


def _warn_if_widget_id_used_as_template() -> None:
    """Widget ids are 24-char hex in the dashboard URL; SendOTP needs OTP → Templates id."""
    tpl = settings.MSG91_TEMPLATE_ID.strip().lower()
    if len(tpl) == 24 and re.fullmatch(r"[0-9a-f]+", tpl):
        log.warning(
            "msg91_template_looks_like_widget_id",
            hint="MSG91_TEMPLATE_ID may be widgetId — use OTP → Templates id with ##OTP## instead",
        )


def _otp_query_params(mobile: str, otp: str) -> dict[str, str]:
    """MSG91 v5 SendOTP expects query params, not a JSON body."""
    _warn_if_widget_id_used_as_template()
    return {
        "template_id": settings.MSG91_TEMPLATE_ID,
        "mobile": mobile,
        "otp": otp,
        "otp_length": "6",
    }


def _extract_request_id(data: dict) -> str | None:
    for key in ("message", "request_id", "reqId"):
        val = data.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return None


def _otp_accepted(resp: httpx.Response, mobile: str) -> bool:
    """True only when MSG91 JSON reports type=success with a non-empty request id."""
    resp.raise_for_status()
    try:
        data = resp.json()
    except ValueError:
        log.error(
            "msg91_otp_bad_response",
            phone=_masked_phone(mobile),
            body=resp.text[:300],
        )
        return False

    if not isinstance(data, dict):
        log.error(
            "msg91_otp_bad_response",
            phone=_masked_phone(mobile),
            body=str(data)[:300],
        )
        return False

    status_type = str(data.get("type", "")).lower()
    request_id = _extract_request_id(data)

    if status_type == "success" and request_id:
        log.info(
            "msg91_otp_sent",
            phone=_masked_phone(mobile),
            request_id=request_id,
        )
        return True

    if status_type == "success" and not request_id:
        log.error(
            "msg91_otp_rejected",
            phone=_masked_phone(mobile),
            error=(
                "MSG91 returned success without request id — use API Auth Key + SendOTP template id "
                "(not OTP Widget tokenAuth / widgetId). See MSG91 dashboard → OTP → Templates + API authkey."
            ),
            body=str(data)[:300],
        )
        return False

    err = data.get("error") or data.get("message") or data
    log.error("msg91_otp_rejected", phone=_masked_phone(mobile), error=str(err)[:300])
    return False


def send_otp_sms_sync(phone: str, otp: str) -> bool:
    """Sync OTP send for workers. Returns True when MSG91 accepted the request."""
    if not settings.MSG91_AUTH_KEY or not settings.MSG91_TEMPLATE_ID:
        return False
    mobile = normalize_india_mobile(phone)
    params = _otp_query_params(mobile, otp)
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.post(_MSG91_OTP_URL, params=params, headers=_headers())
        return _otp_accepted(resp, mobile)
    except httpx.HTTPError as exc:
        log.error("msg91_otp_failed", phone=_masked_phone(mobile), error=str(exc))
        return False


async def send_otp_sms(phone: str, otp: str) -> bool:
    """Async OTP send for auth route handlers."""
    if not settings.MSG91_AUTH_KEY or not settings.MSG91_TEMPLATE_ID:
        return False
    mobile = normalize_india_mobile(phone)
    params = _otp_query_params(mobile, otp)
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(_MSG91_OTP_URL, params=params, headers=_headers())
        return _otp_accepted(resp, mobile)
    except httpx.HTTPError as exc:
        log.error("msg91_otp_failed", phone=_masked_phone(mobile), error=str(exc))
        return False


def send_transactional_sms_sync(phone: str, message: str) -> bool:
    """Transactional SMS (offer alert, no-pujari). Uses Flow API with var1=message."""
    if not settings.MSG91_AUTH_KEY:
        return False
    template_id = settings.MSG91_TXN_TEMPLATE_ID or settings.MSG91_TEMPLATE_ID
    if not template_id:
        return False
    mobile = normalize_india_mobile(phone)
    payload = {
        "template_id": template_id,
        "recipients": [{"mobiles": mobile, "var1": message[:160]}],
    }
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.post(_MSG91_FLOW_URL, json=payload, headers=_headers())
        resp.raise_for_status()
        log.info("msg91_txn_sent", phone=mobile[-4:].rjust(len(mobile), "*"))
        return True
    except httpx.HTTPError as exc:
        log.error("msg91_txn_failed", phone=mobile[-4:].rjust(len(mobile), "*"), error=str(exc))
        return False
