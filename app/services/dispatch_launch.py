"""Launch dispatch policy — windows, settings, eligibility (§21, P-LAUNCH-DISPATCH)."""
from __future__ import annotations

import datetime as dt
import json
import zoneinfo
from dataclasses import dataclass
from typing import Any, Literal

from app.core.config import get_settings

_TZ = zoneinfo.ZoneInfo(get_settings().PLATFORM_TIMEZONE)

BookingClass = Literal["instant", "advance"]


@dataclass(frozen=True)
class LaunchDispatchSettings:
    instant_lead_hours: int = 4
    instant_dispatch_minutes: int = 30
    advance_dispatch_start_hours: int = 4
    advance_dispatch_fail_hours: int = 3
    reoffer_cooldown_minutes: int = 45
    dispatch_buffer_minutes: int = 60
    immediate_dispatch_on_payment: bool = True
    instant_offer_ttl_seconds: int = 120
    advance_offer_ttl_hours: int = 24
    max_live_advance_offers_per_pujari: int = 15
    rm_escalation_hours_no_accept: int = 24
    rm_escalation_t24_hours: int = 24


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


_DISPATCH_SETTING_KEYS = (
    "instant_lead_hours",
    "instant_dispatch_minutes",
    "advance_dispatch_start_hours",
    "advance_dispatch_fail_hours",
    "reoffer_cooldown_minutes",
    "dispatch_buffer_minutes",
    "immediate_dispatch_on_payment",
    "instant_offer_ttl_seconds",
    "advance_offer_ttl_hours",
    "max_live_advance_offers_per_pujari",
    "rm_escalation_hours_no_accept",
    "rm_escalation_t24_hours",
)


def _settings_from_rows(rows: dict[str, Any]) -> LaunchDispatchSettings:
    return LaunchDispatchSettings(
        instant_lead_hours=_int_setting(rows.get("instant_lead_hours"), 4),
        instant_dispatch_minutes=_int_setting(rows.get("instant_dispatch_minutes"), 30),
        advance_dispatch_start_hours=_int_setting(rows.get("advance_dispatch_start_hours"), 4),
        advance_dispatch_fail_hours=_int_setting(rows.get("advance_dispatch_fail_hours"), 3),
        reoffer_cooldown_minutes=_int_setting(rows.get("reoffer_cooldown_minutes"), 45),
        dispatch_buffer_minutes=_int_setting(rows.get("dispatch_buffer_minutes"), 60),
        immediate_dispatch_on_payment=_bool_setting(
            rows.get("immediate_dispatch_on_payment"), True
        ),
        instant_offer_ttl_seconds=_int_setting(rows.get("instant_offer_ttl_seconds"), 120),
        advance_offer_ttl_hours=_int_setting(rows.get("advance_offer_ttl_hours"), 24),
        max_live_advance_offers_per_pujari=_int_setting(
            rows.get("max_live_advance_offers_per_pujari"), 15
        ),
        rm_escalation_hours_no_accept=_int_setting(
            rows.get("rm_escalation_hours_no_accept"), 24
        ),
        rm_escalation_t24_hours=_int_setting(rows.get("rm_escalation_t24_hours"), 24),
    )


def load_dispatch_settings(cur) -> LaunchDispatchSettings:
    """Read platform_settings dispatch keys (sync — Celery workers)."""
    cur.execute(
        "SELECT key, value_json FROM platform_settings WHERE key = ANY(%s)",
        (list(_DISPATCH_SETTING_KEYS),),
    )
    rows = {k: v for k, v in cur.fetchall()}
    return _settings_from_rows(rows)


async def load_dispatch_settings_async(db) -> LaunchDispatchSettings:
    """Read platform_settings dispatch keys (async — API layer)."""
    from sqlalchemy import text

    rows = (
        await db.execute(
            text(
                "SELECT key, value_json FROM platform_settings "
                "WHERE key = ANY(:keys)"
            ),
            {"keys": list(_DISPATCH_SETTING_KEYS)},
        )
    ).all()
    raw = {k: v for k, v in rows}
    return _settings_from_rows(raw)


def slot_datetime(scheduled_date: dt.date, scheduled_time: dt.time) -> dt.datetime:
    return dt.datetime.combine(scheduled_date, scheduled_time, tzinfo=_TZ)


def compute_dispatch_windows(
    scheduled_date: dt.date,
    scheduled_time: dt.time,
    settings: LaunchDispatchSettings,
    *,
    booking_class: BookingClass,
    now: dt.datetime | None = None,
) -> tuple[dt.datetime, dt.datetime]:
    """Class-aware windows from frozen booking_class (§21.6.C)."""
    now_utc = now or dt.datetime.now(dt.UTC)
    now_local = now_utc.astimezone(_TZ)
    slot = slot_datetime(scheduled_date, scheduled_time)

    if booking_class == "instant":
        return (
            now_local,
            now_local + dt.timedelta(minutes=settings.instant_dispatch_minutes),
        )

    if settings.immediate_dispatch_on_payment:
        starts = now_local
    else:
        starts = slot - dt.timedelta(hours=settings.advance_dispatch_start_hours)
    deadline = slot - dt.timedelta(hours=settings.advance_dispatch_fail_hours)
    return starts, deadline


def offer_expires_interval(booking_class: BookingClass, settings: LaunchDispatchSettings) -> str:
    """PostgreSQL interval literal for offer TTL by frozen class (§21.6.D)."""
    if booking_class == "instant":
        return f"{settings.instant_offer_ttl_seconds} seconds"
    return f"{settings.advance_offer_ttl_hours} hours"


def filter_candidates_inbox_cap(
    cur,
    candidate_ids: list,
    cap: int,
) -> tuple[list, int]:
    """G1 inbox cap (§21.6.G): drop pujaris already at live advance-offer limit.

    Counts only unresolved `offered` rows on `booking_class='advance'` bookings.
    Instant-class dispatches must not call this — instant offers are never suppressed.
    """
    if not candidate_ids or cap <= 0:
        return candidate_ids, 0
    cur.execute(
        """
        SELECT ba.pujari_id
        FROM booking_assignments ba
        JOIN bookings b ON b.id = ba.booking_id
        JOIN status_types st ON st.id = ba.status_id
        WHERE ba.pujari_id = ANY(%s)
          AND b.booking_class = 'advance'
          AND ba.responded_at IS NULL
          AND ba.expires_at > now()
          AND st.domain = 'assignment'
          AND st.code = 'offered'
        GROUP BY ba.pujari_id
        HAVING count(*) >= %s
        """,
        (candidate_ids, cap),
    )
    capped = {str(row[0]) for row in cur.fetchall()}
    if not capped:
        return candidate_ids, 0
    return [pid for pid in candidate_ids if str(pid) not in capped], len(capped)


def ensure_dispatch_windows(
    cur, booking_id: str, settings: LaunchDispatchSettings
) -> tuple[dt.datetime, dt.datetime, dt.date, dt.time, BookingClass]:
    """Worker-owned: set dispatch_starts_at / dispatch_deadline once (§21.6.C)."""
    cur.execute(
        """
        SELECT b.scheduled_date, b.scheduled_time, b.booking_class,
               bds.dispatch_starts_at, bds.dispatch_deadline
        FROM bookings b
        LEFT JOIN booking_dispatch_state bds ON bds.booking_id = b.id
        WHERE b.id = %s
        """,
        (booking_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise RuntimeError(f"booking {booking_id} not found")
    scheduled_date, scheduled_time, booking_class, starts_at, deadline = row
    if booking_class not in ("instant", "advance"):
        booking_class = "advance"

    if starts_at is None or deadline is None:
        starts_at, deadline = compute_dispatch_windows(
            scheduled_date,
            scheduled_time,
            settings,
            booking_class=booking_class,
        )
        cur.execute(
            """
            UPDATE booking_dispatch_state
            SET dispatch_starts_at = %s, dispatch_deadline = %s
            WHERE booking_id = %s
            """,
            (starts_at, deadline, booking_id),
        )
    return starts_at, deadline, scheduled_date, scheduled_time, booking_class


def _eligibility_predicates(settings: LaunchDispatchSettings) -> str:
    """Shared citywide filters; `b` must expose id, puja_id, scheduled_date, scheduled_time, duration_minutes."""
    return f"""
          AND EXISTS (
            SELECT 1 FROM pujari_availability pa
            WHERE pa.pujari_id = pj.id
              AND pa.day_of_week = (EXTRACT(ISODOW FROM b.scheduled_date)::int - 1)
              AND pa.start_time <= b.scheduled_time
              AND pa.end_time > b.scheduled_time
          )
          AND NOT EXISTS (
            SELECT 1 FROM pujari_unavailability pu
            WHERE pu.pujari_id = pj.id AND pu.unavailable_date = b.scheduled_date
          )
          AND NOT EXISTS (
            SELECT 1 FROM bookings b2
            WHERE b2.pujari_id = pj.id AND b2.cancelled_at IS NULL AND b2.id != b.id
              AND                   tsrange(b2.scheduled_date + b2.scheduled_time,
                          b2.scheduled_date + b2.scheduled_time
                          + make_interval(mins => b2.duration_minutes))
                  &&
                  tsrange(b.scheduled_date + b.scheduled_time,
                          b.scheduled_date + b.scheduled_time
                          + make_interval(mins => b.duration_minutes))
          )
          AND NOT EXISTS (
            SELECT 1 FROM bookings b3
            WHERE b3.intended_pujari_id = pj.id AND b3.paid_at IS NOT NULL
              AND b3.cancelled_at IS NULL AND b3.id != b.id
              AND                   tsrange(b3.scheduled_date + b3.scheduled_time,
                          b3.scheduled_date + b3.scheduled_time
                          + make_interval(mins => b3.duration_minutes))
                  &&
                  tsrange(b.scheduled_date + b.scheduled_time,
                          b.scheduled_date + b.scheduled_time
                          + make_interval(mins => b.duration_minutes))
          )
          AND NOT EXISTS (
            SELECT 1 FROM bookings b4
            JOIN status_types st4 ON st4.id = b4.status_id
            WHERE b4.pujari_id = pj.id AND b4.cancelled_at IS NULL AND b4.id != b.id
              AND st4.domain = 'booking'
              AND st4.code IN ('confirmed', 'in_progress')
              AND (b4.scheduled_date + b4.scheduled_time
                   + make_interval(mins => b4.duration_minutes))
                  > (b.scheduled_date + b.scheduled_time)
                  - make_interval(mins => {settings.dispatch_buffer_minutes})
              AND (b4.scheduled_date + b4.scheduled_time
                   + make_interval(mins => b4.duration_minutes))
                  <= (b.scheduled_date + b.scheduled_time)
          )
          AND NOT EXISTS (
            SELECT 1 FROM booking_assignments ba
            JOIN status_types st ON st.id = ba.status_id
            WHERE ba.booking_id = b.id AND ba.pujari_id = pj.id
              AND st.domain = 'assignment' AND st.code = 'rejected'
          )
          AND NOT EXISTS (
            SELECT 1 FROM booking_assignments ba
            JOIN status_types st ON st.id = ba.status_id
            WHERE ba.booking_id = b.id AND ba.pujari_id = pj.id
              AND st.domain = 'assignment' AND st.code = 'expired'
              AND ba.responded_at > now() - make_interval(mins => {settings.reoffer_cooldown_minutes})
          )
          AND NOT EXISTS (
            SELECT 1 FROM booking_assignments ba
            WHERE ba.booking_id = b.id AND ba.pujari_id = pj.id
              AND ba.responded_at IS NULL AND ba.expires_at > now()
          )
    """


def launch_eligibility_sql(settings: LaunchDispatchSettings) -> str:
    """Citywide eligibility — no ST_DWithin / pujari_live_location (§21.2)."""
    return f"""
        SELECT pj.id
        FROM bookings b
        JOIN pujaris pj ON pj.verification_status = 'verified'
        JOIN pujari_pricing pp ON pp.pujari_id = pj.id AND pp.puja_id = b.puja_id
        JOIN pujari_service_areas psa ON psa.pujari_id = pj.id
        JOIN service_areas sa ON sa.id = psa.service_area_id AND sa.is_active
        WHERE b.id = %s
        {_eligibility_predicates(settings)}
    """


def launch_eligibility_slot_sql(settings: LaunchDispatchSettings) -> str:
    """Pre-booking supply check — same filters as dispatch, synthetic slot row."""
    return f"""
        SELECT pj.id
        FROM (
            SELECT
                CAST(:puja_id AS uuid) AS puja_id,
                CAST(:scheduled_date AS date) AS scheduled_date,
                CAST(:scheduled_time AS time) AS scheduled_time,
                CAST(:duration_minutes AS int) AS duration_minutes,
                CAST(:exclude_booking_id AS uuid) AS id
        ) b
        JOIN pujaris pj ON pj.verification_status = 'verified'
        JOIN pujari_pricing pp ON pp.pujari_id = pj.id AND pp.puja_id = b.puja_id
        JOIN pujari_service_areas psa ON psa.pujari_id = pj.id
        JOIN service_areas sa ON sa.id = psa.service_area_id AND sa.is_active
        WHERE TRUE
        {_eligibility_predicates(settings)}
    """
