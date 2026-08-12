"""Dispatch v2 booking gate — frozen booking_class + night slot rules (§21.6.A)."""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from typing import Any, Literal

from fastapi import HTTPException, status as http
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.dispatch_launch import _int_setting, slot_datetime

BookingClass = Literal["instant", "advance"]

_INSTANT_NIGHT_MSG = (
    "Instant bookings are not available for night slots (12:00 AM–5:59 AM). "
    "Please choose a later time."
)
_NIGHT_DISABLED_MSG = (
    "Night bookings are not available yet. Please choose a slot at or after 6:00 AM."
)


@dataclass(frozen=True)
class BookingGateSettings:
    instant_lead_hours: int = 4
    night_bookings_enabled: bool = False


@dataclass(frozen=True)
class BookingGateResult:
    booking_class: BookingClass
    lead_hours: float
    is_night: bool


def _bool_setting(raw: Any, default: bool) -> bool:
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    if isinstance(raw, dict) and "value" in raw:
        return _bool_setting(raw["value"], default)
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return raw.strip().lower() in {"true", "1", "yes"}
        return _bool_setting(parsed, default)
    return default


def is_night_slot(scheduled_time: dt.time) -> bool:
    """True when scheduled_time is 00:00–05:59 IST wall clock (§21.6.A)."""
    return dt.time(0, 0) <= scheduled_time < dt.time(6, 0)


def compute_lead_hours(
    scheduled_date: dt.date,
    scheduled_time: dt.time,
    *,
    now: dt.datetime | None = None,
) -> float:
    now_utc = now or dt.datetime.now(dt.UTC)
    now_local = now_utc.astimezone(slot_datetime(scheduled_date, scheduled_time).tzinfo)
    slot = slot_datetime(scheduled_date, scheduled_time)
    return (slot - now_local).total_seconds() / 3600.0


def compute_booking_class(lead_hours: float, instant_lead_hours: int) -> BookingClass:
    return "instant" if lead_hours <= instant_lead_hours else "advance"


def evaluate_booking_gate(
    scheduled_date: dt.date,
    scheduled_time: dt.time,
    settings: BookingGateSettings,
    *,
    now: dt.datetime | None = None,
) -> BookingGateResult:
    """Classify the slot and return advisory metadata (no HTTP errors)."""
    lead_hours = compute_lead_hours(scheduled_date, scheduled_time, now=now)
    booking_class = compute_booking_class(lead_hours, settings.instant_lead_hours)
    night = is_night_slot(scheduled_time)
    return BookingGateResult(
        booking_class=booking_class,
        lead_hours=lead_hours,
        is_night=night,
    )


def night_gate_error_code(
    booking_class: BookingClass,
    is_night: bool,
    night_bookings_enabled: bool,
) -> str | None:
    if is_night and booking_class == "instant":
        return "INSTANT_NIGHT_BLOCKED"
    if is_night and not night_bookings_enabled:
        return "NIGHT_BOOKINGS_DISABLED"
    return None


def gate_warning_message(code: str) -> str:
    if code == "INSTANT_NIGHT_BLOCKED":
        return _INSTANT_NIGHT_MSG
    if code == "NIGHT_BOOKINGS_DISABLED":
        return _NIGHT_DISABLED_MSG
    return "This slot cannot be booked."


def gate_warning_payload(code: str) -> dict[str, str]:
    return {"code": code, "message": gate_warning_message(code)}


def assert_booking_gate(
    scheduled_date: dt.date,
    scheduled_time: dt.time,
    settings: BookingGateSettings,
    *,
    now: dt.datetime | None = None,
) -> BookingGateResult:
    """Authoritative gate for POST /v1/bookings — raises 422 before payment."""
    result = evaluate_booking_gate(
        scheduled_date, scheduled_time, settings, now=now
    )
    code = night_gate_error_code(
        result.booking_class, result.is_night, settings.night_bookings_enabled
    )
    if code is not None:
        raise HTTPException(
            http.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=gate_warning_payload(code),
        )
    return result


async def load_booking_gate_settings(db: AsyncSession) -> BookingGateSettings:
    rows = (
        await db.execute(
            text(
                "SELECT key, value_json FROM platform_settings "
                "WHERE key IN ('instant_lead_hours', 'night_bookings_enabled')"
            )
        )
    ).all()
    raw = {k: v for k, v in rows}
    return BookingGateSettings(
        instant_lead_hours=_int_setting(raw.get("instant_lead_hours"), 4),
        night_bookings_enabled=_bool_setting(raw.get("night_bookings_enabled"), False),
    )
