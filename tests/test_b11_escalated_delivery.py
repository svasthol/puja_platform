"""B11 + round-6 urgent exception — policy matrix (plan §6)."""
from __future__ import annotations

import datetime as dt
import zoneinfo

from app.services.dispatch_launch import LaunchDispatchSettings, compute_dispatch_windows, slot_datetime
from app.services.escalated_delivery import (
    EscalatedDeliveryPolicy,
    compute_escalated_offer_expires_at,
    escalated_delivery_policy,
)

_TZ = zoneinfo.ZoneInfo("Asia/Kolkata")
_QUIET_START = dt.time(22, 0)
_QUIET_END = dt.time(8, 0)
_ESCALATED_TTL = 900


def _dispatch_deadline(slot: dt.datetime) -> dt.datetime:
    """Advance class deadline = slot − advance_dispatch_fail_hours (default 3h)."""
    settings = LaunchDispatchSettings()
    _start, deadline = compute_dispatch_windows(
        slot.date(),
        slot.time(),
        settings,
        booking_class="advance",
    )
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=_TZ)
    return deadline


def test_b11_quiet_23h_pay_14h_slot_defer_high_push():
    """Born-escalated 23:00 for 14:00 slot: no high in quiet; quiet expiry path."""
    now = dt.datetime(2026, 7, 23, 23, 0, tzinfo=_TZ)
    slot = slot_datetime(dt.date(2026, 7, 24), dt.time(14, 0))
    deadline = _dispatch_deadline(slot)

    policy = escalated_delivery_policy(
        now,
        quiet_start=_QUIET_START,
        quiet_end=_QUIET_END,
        dispatch_deadline=deadline,
    )
    assert policy.in_quiet
    assert policy.allow_high_push is False
    assert policy.use_quiet_offer_expiry is True
    assert policy.allow_holder_shorten is False

    expires = compute_escalated_offer_expires_at(
        now,
        policy,
        quiet_end=_QUIET_END,
        escalated_ttl_seconds=_ESCALATED_TTL,
        dispatch_deadline=deadline,
    )
    quiet_end_dt = dt.datetime(2026, 7, 24, 8, 0, tzinfo=_TZ)
    assert expires <= deadline
    assert expires >= quiet_end_dt


def test_b11_quiet_23h_pay_07h_slot_urgent_exception_high_push():
    """Urgent: deadline 04:00 < quiet_end 08:00 → high allowed in quiet + shorten."""
    now = dt.datetime(2026, 7, 23, 23, 0, tzinfo=_TZ)
    slot = slot_datetime(dt.date(2026, 7, 24), dt.time(7, 0))
    deadline = _dispatch_deadline(slot)
    assert deadline.hour == 4

    policy = escalated_delivery_policy(
        now,
        quiet_start=_QUIET_START,
        quiet_end=_QUIET_END,
        dispatch_deadline=deadline,
    )
    assert policy.in_quiet
    assert policy.urgent is True
    assert policy.allow_high_push is True
    assert policy.allow_holder_shorten is True
    assert policy.use_quiet_offer_expiry is False

    expires = compute_escalated_offer_expires_at(
        now,
        policy,
        quiet_end=_QUIET_END,
        escalated_ttl_seconds=900,
        dispatch_deadline=deadline,
    )
    assert expires <= deadline


def test_b11_daytime_full_escalated_policy():
    now = dt.datetime(2026, 7, 24, 10, 0, tzinfo=_TZ)
    slot = slot_datetime(dt.date(2026, 7, 24), dt.time(20, 0))
    deadline = _dispatch_deadline(slot)
    policy = escalated_delivery_policy(
        now,
        quiet_start=_QUIET_START,
        quiet_end=_QUIET_END,
        dispatch_deadline=deadline,
    )
    assert not policy.in_quiet
    assert policy.allow_holder_shorten
    assert policy.allow_high_push
    assert not policy.use_quiet_offer_expiry