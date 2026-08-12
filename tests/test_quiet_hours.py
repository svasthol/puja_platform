"""DV2-QUIET-HOURS — reconfirm ping/escalation quiet-window shifting (§21.6.H)."""
from __future__ import annotations

import datetime as dt
import zoneinfo

import pytest

from app.services.reconfirmation import (
    ReconfirmSettings,
    effective_escalation_at,
    effective_ping_at,
    is_quiet_hours,
    parse_hhmm,
    preceding_quiet_start,
)

_TZ = zoneinfo.ZoneInfo("Asia/Kolkata")


def test_parse_hhmm_from_json_string():
    assert parse_hhmm('"22:00"', dt.time(0, 0)) == dt.time(22, 0)
    assert parse_hhmm("08:00", dt.time(0, 0)) == dt.time(8, 0)


def test_is_quiet_hours_overnight_window():
    assert is_quiet_hours(dt.datetime(2026, 7, 23, 23, 0, tzinfo=_TZ), dt.time(22, 0), dt.time(8, 0))
    assert is_quiet_hours(dt.datetime(2026, 7, 23, 3, 0, tzinfo=_TZ), dt.time(22, 0), dt.time(8, 0))
    assert not is_quiet_hours(dt.datetime(2026, 7, 23, 12, 0, tzinfo=_TZ), dt.time(22, 0), dt.time(8, 0))


def test_effective_ping_shifts_nominal_inside_quiet_earlier():
    settings = ReconfirmSettings()
    slot = dt.datetime(2026, 7, 24, 2, 0, tzinfo=_TZ)
    nominal = slot - dt.timedelta(hours=24)
    effective = effective_ping_at(slot, settings)
    assert is_quiet_hours(nominal, settings.quiet_hours_start, settings.quiet_hours_end)
    assert effective == dt.datetime(2026, 7, 22, 22, 0, tzinfo=_TZ)
    assert effective < nominal


def test_effective_ping_unchanged_outside_quiet():
    settings = ReconfirmSettings()
    slot = dt.datetime(2026, 7, 24, 14, 0, tzinfo=_TZ)
    effective = effective_ping_at(slot, settings)
    assert effective == slot - dt.timedelta(hours=24)


def test_effective_escalation_clamped_past_quiet_end_when_base_in_quiet():
    settings = ReconfirmSettings(escalation_hours=4)
    ping_sent = dt.datetime(2026, 7, 23, 21, 0, tzinfo=_TZ)
    base = ping_sent + dt.timedelta(hours=4)  # 01:00 — inside quiet
    effective = effective_escalation_at(ping_sent, settings)
    assert base.hour == 1
    assert effective == dt.datetime(2026, 7, 24, 8, 0, tzinfo=_TZ)


def test_effective_escalation_unchanged_when_base_outside_quiet():
    settings = ReconfirmSettings(escalation_hours=4)
    ping_sent = dt.datetime(2026, 7, 23, 10, 0, tzinfo=_TZ)
    effective = effective_escalation_at(ping_sent, settings)
    assert effective == dt.datetime(2026, 7, 23, 14, 0, tzinfo=_TZ)


def test_preceding_quiet_start_same_evening():
    local = dt.datetime(2026, 7, 23, 23, 30, tzinfo=_TZ)
    assert preceding_quiet_start(local, dt.time(22, 0)) == dt.datetime(
        2026, 7, 23, 22, 0, tzinfo=_TZ
    )
