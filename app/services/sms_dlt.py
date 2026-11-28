"""
TRAI DLT SMS — Jio-approved template text and variable hygiene.

Approved templates (MNGURU, Service Implicit):
  - Mana Guruji Verification OTP — single {#number#}
  - Mana Guruji Booking — three {#alphanumeric#} (puja name, slot, ref)

Fast2SMS delivery uses either:
  - route=dlt + panel Message ID + pipe-separated variables (preferred), or
  - route=dlt_manual + Entity ID + 19-digit Content Template ID + exact final text

Manual text MUST match the DLT registration character-for-character (newlines included).
"""
from __future__ import annotations

import datetime as dt
import re
import uuid

import structlog

from app.core.config import get_settings

log = structlog.get_logger()

DLT_ALPHANUM_MAX_LEN = 40
DLT_OTP_VALID_MINUTES = 5

# Jio Content Template IDs (19-digit) — from Principal Entity portal.
DLT_OTP_CONTENT_TEMPLATE_ID = "1277179571901507630"
DLT_BOOKING_CONTENT_TEMPLATE_ID = "1277179571625152309"


def resolved_otp_template_id() -> str:
    s = get_settings()
    return s.FAST2SMS_DLT_OTP_TEMPLATE_ID.strip() or DLT_OTP_CONTENT_TEMPLATE_ID


def resolved_booking_template_id() -> str:
    s = get_settings()
    return (
        s.FAST2SMS_DLT_BOOKING_TEMPLATE_ID.strip() or DLT_BOOKING_CONTENT_TEMPLATE_ID
    )


def dlt_otp_ready() -> bool:
    s = get_settings()
    if not s.FAST2SMS_API_KEY or not s.FAST2SMS_SENDER_ID.strip():
        return False
    if s.FAST2SMS_DLT_OTP_MESSAGE_ID.strip():
        return True
    return bool(s.FAST2SMS_DLT_ENTITY_ID.strip() and resolved_otp_template_id())


def dlt_booking_ready() -> bool:
    s = get_settings()
    if not s.FAST2SMS_API_KEY or not s.FAST2SMS_SENDER_ID.strip():
        return False
    if s.FAST2SMS_DLT_BOOKING_MESSAGE_ID.strip():
        return True
    return bool(s.FAST2SMS_DLT_ENTITY_ID.strip() and resolved_booking_template_id())


def warn_if_otp_ttl_mismatch() -> None:
    s = get_settings()
    if not dlt_otp_ready():
        return
    if s.OTP_EXPIRE_MINUTES != DLT_OTP_VALID_MINUTES:
        log.warning(
            "dlt_otp_ttl_mismatch",
            otp_expire_minutes=s.OTP_EXPIRE_MINUTES,
            dlt_template_minutes=DLT_OTP_VALID_MINUTES,
            hint="Set OTP_EXPIRE_MINUTES=5 to match the approved DLT OTP template.",
        )


def sanitize_dlt_number(otp: str) -> str | None:
    """OTP slot {#number#} — digits only (6-digit login codes)."""
    digits = re.sub(r"\D", "", otp or "")
    if len(digits) != 6:
        return None
    return digits


def sanitize_dlt_alphanumeric(value: str, *, field: str) -> str:
    """
    {#alphanumeric#} — max 40 chars; no leading URL; no pipe (Fast2SMS separator).
    """
    text = " ".join((value or "").split()).strip()
    if not text:
        return ""
    lower = text.lower()
    if lower.startswith(("http://", "https://", "www.")):
        log.warning("dlt_alphanumeric_rejected_url_prefix", field=field)
        text = text.split(":", 1)[-1].lstrip("/")
        text = " ".join(text.split()).strip()
    text = text.replace("|", " ")
    if len(text) > DLT_ALPHANUM_MAX_LEN:
        log.warning(
            "dlt_alphanumeric_truncated",
            field=field,
            original_len=len(text),
        )
        text = text[:DLT_ALPHANUM_MAX_LEN].rstrip()
    return text


def booking_public_ref(booking_id: str | uuid.UUID) -> str:
    """Short ref for Ref {#alphanumeric#} — fits DLT 40-char limit."""
    try:
        uid = booking_id if isinstance(booking_id, uuid.UUID) else uuid.UUID(str(booking_id))
    except (ValueError, TypeError, AttributeError):
        hex_only = re.sub(r"[^0-9a-fA-F]", "", str(booking_id))[:8]
        return (hex_only or "00000000").upper()
    return uid.hex[:8].upper()


def format_booking_slot_label(scheduled_date: dt.date, scheduled_time: dt.time) -> str:
    """Align with Jio sample: `28 Nov 2026, 7:30 AM`."""
    month = scheduled_date.strftime("%b")
    date_part = f"{scheduled_date.day} {month} {scheduled_date.year}"
    hour24 = scheduled_time.hour
    am_pm = "AM" if hour24 < 12 else "PM"
    hour12 = hour24 % 12 or 12
    if scheduled_time.minute:
        time_part = f"{hour12}:{scheduled_time.minute:02d} {am_pm}"
    else:
        time_part = f"{hour12} {am_pm}"
    return f"{date_part}, {time_part}"


def join_dlt_variables(*values: str) -> str:
    return "|".join(values)


def build_dlt_otp_message(otp: str) -> str:
    """
    Final SMS body for dlt_manual — must match Jio-approved layout.
    """
    code = sanitize_dlt_number(otp)
    if code is None:
        raise ValueError("invalid_otp_for_dlt")
    return (
        f"Dear User,\n"
        f"{code} is your OTP for Mana Guruji verification. "
        f"Valid for {DLT_OTP_VALID_MINUTES} minutes. "
        f"Please do not share this code with anyone.\n"
        f"Thanks,\n"
        f"Mana Guruji Team"
    )


def build_dlt_booking_message(puja_name: str, slot_label: str, ref: str) -> str:
    puja = sanitize_dlt_alphanumeric(puja_name, field="puja_name")
    when = sanitize_dlt_alphanumeric(slot_label, field="slot")
    booking_ref = sanitize_dlt_alphanumeric(ref, field="ref")
    if not puja or not when or not booking_ref:
        raise ValueError("incomplete_booking_dlt_fields")
    return (
        f"Dear User,\n"
        f"Your {puja} booking is confirmed on {when}. "
        f"Ref {booking_ref}. View details in the Mana Guruji app.\n"
        f"Thanks,\n"
        f"Mana Guruji Team"
    )