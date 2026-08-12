"""Advance booking reconfirmation policy (§21.7, P-LAUNCH-RECONFIRM)."""
from __future__ import annotations

import datetime as dt
import json
import zoneinfo
from dataclasses import dataclass
from typing import Any

from app.core.config import get_settings

_TZ = zoneinfo.ZoneInfo(get_settings().PLATFORM_TIMEZONE)

# Worst-case quiet shift: nominal ping at 07:59 → preceding 22:00 two days earlier (~34h before slot).
_QUIET_PING_LOOKBACK_EXTRA_HOURS = 10


@dataclass(frozen=True)
class ReconfirmSettings:
    lead_hours: int = 24
    ping_hours_before_slot: int = 24
    escalation_hours: int = 4
    quiet_hours_start: dt.time = dt.time(22, 0)
    quiet_hours_end: dt.time = dt.time(8, 0)


def _int_setting(raw: Any, default: int) -> int:
    if raw is None:
        return default
    if isinstance(raw, (int, float)):
        return int(raw)
    if isinstance(raw, dict) and "value" in raw:
        return int(raw["value"])
    if isinstance(raw, str):
        try:
            return int(json.loads(raw))
        except json.JSONDecodeError:
            return int(raw)
    return default


def parse_hhmm(raw: Any, default: dt.time) -> dt.time:
    """Parse platform_settings quiet-hours value (`"22:00"` or json-encoded)."""
    if raw is None:
        return default
    if isinstance(raw, dt.time):
        return raw
    text = raw
    if isinstance(raw, dict) and "value" in raw:
        text = raw["value"]
    if not isinstance(text, str):
        return default
    text = text.strip().strip('"')
    try:
        parsed = json.loads(text)
        if isinstance(parsed, str):
            text = parsed.strip()
    except json.JSONDecodeError:
        pass
    parts = text.split(":")
    if len(parts) != 2:
        return default
    hour, minute = int(parts[0]), int(parts[1])
    return dt.time(hour, minute)


def load_reconfirm_settings(cur) -> ReconfirmSettings:
    keys = (
        "reconfirm_lead_hours",
        "reconfirm_ping_hours_before_slot",
        "reconfirm_escalation_hours",
        "reconfirm_quiet_hours_start",
        "reconfirm_quiet_hours_end",
    )
    cur.execute(
        "SELECT key, value_json FROM platform_settings WHERE key = ANY(%s)",
        (list(keys),),
    )
    rows = {k: v for k, v in cur.fetchall()}
    return ReconfirmSettings(
        lead_hours=_int_setting(rows.get("reconfirm_lead_hours"), 24),
        ping_hours_before_slot=_int_setting(rows.get("reconfirm_ping_hours_before_slot"), 24),
        escalation_hours=_int_setting(rows.get("reconfirm_escalation_hours"), 4),
        quiet_hours_start=parse_hhmm(rows.get("reconfirm_quiet_hours_start"), dt.time(22, 0)),
        quiet_hours_end=parse_hhmm(rows.get("reconfirm_quiet_hours_end"), dt.time(8, 0)),
    )


def is_quiet_hours(
    local_dt: dt.datetime,
    quiet_start: dt.time,
    quiet_end: dt.time,
) -> bool:
    """True when local_dt falls in [quiet_start, quiet_end) — supports overnight windows."""
    t = local_dt.timetz().replace(tzinfo=None) if local_dt.tzinfo else local_dt.time()
    if quiet_start < quiet_end:
        return quiet_start <= t < quiet_end
    return t >= quiet_start or t < quiet_end


def preceding_quiet_start(local_dt: dt.datetime, quiet_start: dt.time) -> dt.datetime:
    """Move to the preceding quiet_start (more lead is always safe — §21.6.H)."""
    tz = local_dt.tzinfo
    day = local_dt.date()
    candidate = dt.datetime.combine(day, quiet_start, tzinfo=tz)
    if local_dt >= candidate:
        return candidate
    return dt.datetime.combine(day - dt.timedelta(days=1), quiet_start, tzinfo=tz)


def next_quiet_end_on_or_after(local_dt: dt.datetime, quiet_end: dt.time) -> dt.datetime:
    """Next quiet_hours_end at or after local_dt."""
    tz = local_dt.tzinfo
    day = local_dt.date()
    candidate = dt.datetime.combine(day, quiet_end, tzinfo=tz)
    if local_dt <= candidate:
        return candidate
    return dt.datetime.combine(day + dt.timedelta(days=1), quiet_end, tzinfo=tz)


def effective_ping_at(
    slot_local: dt.datetime,
    settings: ReconfirmSettings,
) -> dt.datetime:
    """Nominal T−ping_hours, shifted earlier if inside quiet window."""
    nominal = slot_local - dt.timedelta(hours=settings.ping_hours_before_slot)
    if not is_quiet_hours(nominal, settings.quiet_hours_start, settings.quiet_hours_end):
        return nominal
    return preceding_quiet_start(nominal, settings.quiet_hours_start)


def effective_escalation_at(
    ping_sent_at: dt.datetime,
    settings: ReconfirmSettings,
) -> dt.datetime:
    """max(ping+escalation_hours, next quiet_end) when base lands in quiet (§21.6.H)."""
    base = ping_sent_at + dt.timedelta(hours=settings.escalation_hours)
    if not is_quiet_hours(base, settings.quiet_hours_start, settings.quiet_hours_end):
        return base
    return next_quiet_end_on_or_after(base, settings.quiet_hours_end)


def slot_local_expr(alias: str = "b") -> str:
    """Booking slot as timestamptz in platform timezone."""
    return (
        f"(({alias}.scheduled_date + {alias}.scheduled_time) "
        f"AT TIME ZONE '{_TZ.key}')"
    )


def confirmed_at_subquery(alias: str = "b") -> str:
    return f"""
        (
            SELECT MIN(h.changed_at)
            FROM booking_status_history h
            JOIN status_types stc ON stc.id = h.status_id
            WHERE h.booking_id = {alias}.id
              AND stc.domain = 'booking'
              AND stc.code = 'confirmed'
        )
    """


def bookings_needing_ping_sql(settings: ReconfirmSettings) -> str:
    slot = slot_local_expr("b")
    confirmed_at = confirmed_at_subquery("b")
    lookback = settings.ping_hours_before_slot + _QUIET_PING_LOOKBACK_EXTRA_HOURS
    return f"""
        SELECT b.id,
               {slot} AS slot_at
        FROM bookings b
        JOIN status_types st ON st.id = b.status_id
        WHERE st.domain = 'booking' AND st.code = 'confirmed'
          AND b.pujari_id IS NOT NULL
          AND b.cancelled_at IS NULL
          AND {slot} > now()
          AND now() >= {slot} - make_interval(hours => {lookback})
          AND {confirmed_at} IS NOT NULL
          AND ({slot} - {confirmed_at}) >= make_interval(hours => {settings.lead_hours})
          AND NOT EXISTS (
            SELECT 1 FROM booking_reconfirmations br
            WHERE br.booking_id = b.id AND br.ping_sent_at IS NOT NULL
          )
        FOR UPDATE OF b SKIP LOCKED
    """


def bookings_needing_escalation_sql(settings: ReconfirmSettings) -> str:
    return f"""
        SELECT b.id, br.ping_sent_at
        FROM bookings b
        JOIN status_types st ON st.id = b.status_id
        JOIN booking_reconfirmations br ON br.booking_id = b.id
        WHERE st.domain = 'booking' AND st.code = 'confirmed'
          AND b.pujari_id IS NOT NULL
          AND b.cancelled_at IS NULL
          AND br.ping_sent_at IS NOT NULL
          AND br.pujari_confirmed_at IS NULL
          AND br.rm_alert_sent_at IS NULL
        FOR UPDATE OF br SKIP LOCKED
    """
