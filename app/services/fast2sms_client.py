"""
FAST2SMS client — DLT-compliant OTP + booking SMS (MNGURU) with legacy dev fallbacks.

Production (India): route=dlt or route=dlt_manual per Fast2SMS DLT Manager.
  https://www.fast2sms.com/help/dlt-sms-api-guide/

Legacy (no DLT config):
  - OTP:  route=otp, variables_values=<6-digit>
  - Txn:  route=q Quick SMS (non-DLT fallbacks in workers only)
"""
from __future__ import annotations

import httpx
import structlog

from app.core.config import get_settings
from app.services import sms_dlt
from app.services.sms_phone import normalize_india_mobile_ten

log = structlog.get_logger()

_BULK_URL = "https://www.fast2sms.com/dev/bulkV2"
_TIMEOUT = httpx.Timeout(connect=3.0, read=8.0, write=3.0, pool=3.0)
_ROUTE_DLT = "dlt"
_ROUTE_DLT_MANUAL = "dlt_manual"


def _headers() -> dict[str, str]:
    return {"authorization": get_settings().FAST2SMS_API_KEY}


def _masked(phone: str) -> str:
    return phone[-4:].rjust(len(phone), "*")


def _configured() -> bool:
    return bool(get_settings().FAST2SMS_API_KEY)


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


def _post_bulk(payload: dict[str, str], *, phone: str, kind: str) -> bool:
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.post(_BULK_URL, data=payload, headers=_headers())
        return _accepted(resp, phone=phone, kind=kind)
    except httpx.HTTPError as exc:
        log.error("fast2sms_request_failed", kind=kind, phone=_masked(phone), error=str(exc))
        return False


def _send_dlt_template(
    mobile: str,
    *,
    kind: str,
    message_id: str,
    variables_values: str,
) -> bool:
    sender = get_settings().FAST2SMS_SENDER_ID.strip()
    payload = {
        "route": _ROUTE_DLT,
        "sender_id": sender,
        "message": message_id,
        "variables_values": variables_values,
        "numbers": mobile,
    }
    return _post_bulk(payload, phone=mobile, kind=kind)


def _send_dlt_manual(
    mobile: str,
    *,
    kind: str,
    body: str,
    template_id: str,
) -> bool:
    entity_id = get_settings().FAST2SMS_DLT_ENTITY_ID.strip()
    sender = get_settings().FAST2SMS_SENDER_ID.strip()
    if not entity_id or not template_id or not sender:
        log.error("fast2sms_dlt_manual_missing_config", kind=kind)
        return False
    payload = {
        "route": _ROUTE_DLT_MANUAL,
        "sender_id": sender,
        "message": body,
        "entity_id": entity_id,
        "template_id": template_id,
        "numbers": mobile,
        "language": "english",
    }
    return _post_bulk(payload, phone=mobile, kind=kind)


def send_otp_sms_sync(phone: str, otp: str) -> bool:
    if not _configured():
        return False
    mobile = normalize_india_mobile_ten(phone)
    sms_dlt.warn_if_otp_ttl_mismatch()

    if sms_dlt.dlt_otp_ready():
        code = sms_dlt.sanitize_dlt_number(otp)
        if code is None:
            log.error("fast2sms_otp_invalid_digits", phone=_masked(mobile))
            return False
        msg_id = get_settings().FAST2SMS_DLT_OTP_MESSAGE_ID.strip()
        if msg_id:
            return _send_dlt_template(
                mobile,
                kind="dlt_otp",
                message_id=msg_id,
                variables_values=code,
            )
        try:
            body = sms_dlt.build_dlt_otp_message(code)
        except ValueError:
            return False
        return _send_dlt_manual(
            mobile,
            kind="dlt_otp_manual",
            body=body,
            template_id=sms_dlt.resolved_otp_template_id(),
        )

    payload = {
        "route": get_settings().FAST2SMS_OTP_ROUTE,
        "variables_values": otp,
        "numbers": mobile,
    }
    return _post_bulk(payload, phone=mobile, kind="otp_legacy")


def send_booking_confirmed_sms_sync(
    phone: str,
    *,
    puja_name: str,
    scheduled_date,
    scheduled_time,
    booking_id: str,
) -> bool:
    """Customer SMS after pujari accept — Jio 'Mana Guruji Booking' template."""
    if not _configured():
        return False
    if not sms_dlt.dlt_booking_ready():
        log.info("fast2sms_booking_dlt_not_configured", booking_id=booking_id[:8])
        return False

    mobile = normalize_india_mobile_ten(phone)
    slot = sms_dlt.format_booking_slot_label(scheduled_date, scheduled_time)
    ref = sms_dlt.booking_public_ref(booking_id)
    try:
        puja = sms_dlt.sanitize_dlt_alphanumeric(puja_name, field="puja_name")
        when = sms_dlt.sanitize_dlt_alphanumeric(slot, field="slot")
        booking_ref = sms_dlt.sanitize_dlt_alphanumeric(ref, field="ref")
        if not puja or not when or not booking_ref:
            log.error("fast2sms_booking_dlt_empty_field", booking_id=booking_id[:8])
            return False
        variables = sms_dlt.join_dlt_variables(puja, when, booking_ref)
        body = sms_dlt.build_dlt_booking_message(puja, when, booking_ref)
    except ValueError:
        return False

    msg_id = get_settings().FAST2SMS_DLT_BOOKING_MESSAGE_ID.strip()
    if msg_id:
        return _send_dlt_template(
            mobile,
            kind="dlt_booking",
            message_id=msg_id,
            variables_values=variables,
        )
    return _send_dlt_manual(
        mobile,
        kind="dlt_booking_manual",
        body=body,
        template_id=sms_dlt.resolved_booking_template_id(),
    )


def send_transactional_sms_sync(phone: str, message: str) -> bool:
    """Quick SMS route — non-DLT worker fallbacks only (offers, RM alerts)."""
    if not _configured():
        return False
    mobile = normalize_india_mobile_ten(phone)
    payload = {
        "route": get_settings().FAST2SMS_QUICK_ROUTE,
        "message": message[:160],
        "language": "english",
        "numbers": mobile,
    }
    return _post_bulk(payload, phone=mobile, kind="txn_quick")