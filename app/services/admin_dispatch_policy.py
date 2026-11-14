"""Admin read/write for launch dispatch platform_settings (DISPATCH_FLOW, migration 012/014)."""
from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.dispatch_launch import (
    DISPATCH_PLATFORM_SETTING_KEYS,
    LaunchDispatchSettings,
    _bool_setting,
    _settings_from_rows,
)
from app.services.reconfirmation import parse_hhmm

_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):[0-5]\d$")

_ADMIN_DISPATCH_EXTRA_KEYS = (
    "night_bookings_enabled",
    "reconfirm_quiet_hours_start",
    "reconfirm_quiet_hours_end",
)

ADMIN_DISPATCH_POLICY_KEYS: tuple[str, ...] = (
    *DISPATCH_PLATFORM_SETTING_KEYS,
    *_ADMIN_DISPATCH_EXTRA_KEYS,
)

AUDIT_ENTITY_ID = "dispatch_policy"


@dataclass(frozen=True)
class DispatchPolicyView:
  """Flattened policy for admin GET/PUT — mirrors worker + booking-gate consumers."""

  instant_lead_hours: int
  instant_dispatch_minutes: int
  advance_dispatch_start_hours: int
  advance_dispatch_fail_hours: int
  reoffer_cooldown_minutes: int
  dispatch_buffer_minutes: int
  immediate_dispatch_on_payment: bool
  instant_offer_ttl_seconds: int
  advance_offer_ttl_hours: int
  max_live_advance_offers_per_pujari: int
  rm_escalation_hours_no_accept: int
  rm_escalation_t24_hours: int
  night_bookings_enabled: bool
  reconfirm_quiet_hours_start: str
  reconfirm_quiet_hours_end: str
  updated_at: str | None = None


def _hhmm_to_json(value: str) -> str:
    if not _TIME_RE.match(value.strip()):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Quiet hours must be HH:MM (24h), e.g. 22:00",
        )
    return json.dumps(value.strip())


def _hhmm_from_row(raw: Any, default: dt.time) -> str:
    t = parse_hhmm(raw, default)
    return t.strftime("%H:%M")


def _validate_policy(view: DispatchPolicyView) -> None:
    if view.advance_dispatch_fail_hours >= view.advance_dispatch_start_hours + view.instant_lead_hours:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "advance_dispatch_fail_hours is unusually large relative to start/lead; check slot fail window.",
        )
    if view.instant_offer_ttl_seconds >= view.instant_dispatch_minutes * 60:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "instant_offer_ttl_seconds should stay below instant_dispatch_minutes window.",
        )


def _dispatch_json_value(key: str, view: DispatchPolicyView) -> Any:
    if key == "immediate_dispatch_on_payment" or key == "night_bookings_enabled":
        return getattr(view, key)
    if key in ("reconfirm_quiet_hours_start", "reconfirm_quiet_hours_end"):
        return getattr(view, key)
    return getattr(view, key)


def _rows_to_value_json(key: str, view: DispatchPolicyView) -> Any:
    val = _dispatch_json_value(key, view)
    if key in ("reconfirm_quiet_hours_start", "reconfirm_quiet_hours_end"):
        return json.loads(_hhmm_to_json(str(val)))
    if isinstance(val, bool):
        return val
    return int(val)


async def fetch_dispatch_policy(db: AsyncSession) -> DispatchPolicyView:
    rows = (
        await db.execute(
            text(
                "SELECT key, value_json, updated_at FROM platform_settings "
                "WHERE key = ANY(:keys)"
            ),
            {"keys": list(ADMIN_DISPATCH_POLICY_KEYS)},
        )
    ).mappings().all()
    by_key: dict[str, Any] = {}
    updated_at: dt.datetime | None = None
    for row in rows:
        by_key[row["key"]] = row["value_json"]
        ts = row.get("updated_at")
        if ts is not None and (updated_at is None or ts > updated_at):
            updated_at = ts

    launch: LaunchDispatchSettings = _settings_from_rows(by_key)
    return DispatchPolicyView(
        instant_lead_hours=launch.instant_lead_hours,
        instant_dispatch_minutes=launch.instant_dispatch_minutes,
        advance_dispatch_start_hours=launch.advance_dispatch_start_hours,
        advance_dispatch_fail_hours=launch.advance_dispatch_fail_hours,
        reoffer_cooldown_minutes=launch.reoffer_cooldown_minutes,
        dispatch_buffer_minutes=launch.dispatch_buffer_minutes,
        immediate_dispatch_on_payment=launch.immediate_dispatch_on_payment,
        instant_offer_ttl_seconds=launch.instant_offer_ttl_seconds,
        advance_offer_ttl_hours=launch.advance_offer_ttl_hours,
        max_live_advance_offers_per_pujari=launch.max_live_advance_offers_per_pujari,
        rm_escalation_hours_no_accept=launch.rm_escalation_hours_no_accept,
        rm_escalation_t24_hours=launch.rm_escalation_t24_hours,
        night_bookings_enabled=_bool_setting(by_key.get("night_bookings_enabled"), False),
        reconfirm_quiet_hours_start=_hhmm_from_row(
            by_key.get("reconfirm_quiet_hours_start"), dt.time(22, 0)
        ),
        reconfirm_quiet_hours_end=_hhmm_from_row(
            by_key.get("reconfirm_quiet_hours_end"), dt.time(8, 0)
        ),
        updated_at=str(updated_at) if updated_at else None,
    )


async def persist_dispatch_policy(db: AsyncSession, view: DispatchPolicyView) -> DispatchPolicyView:
    _validate_policy(view)
    for key in ADMIN_DISPATCH_POLICY_KEYS:
        value_json = _rows_to_value_json(key, view)
        await db.execute(
            text(
                """
                INSERT INTO platform_settings (key, value_json, updated_at)
                VALUES (:key, CAST(:vj AS jsonb), now())
                ON CONFLICT (key) DO UPDATE SET
                    value_json = CAST(:vj AS jsonb),
                    updated_at = now()
                """
            ),
            {"key": key, "vj": json.dumps(value_json)},
        )
    return await fetch_dispatch_policy(db)