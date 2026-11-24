"""Escalated dispatch delivery policy — quiet hours, urgent exception (B11)."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from app.services.reconfirmation import (
    is_quiet_hours,
    next_quiet_end_on_or_after,
    preceding_quiet_start,
)


@dataclass(frozen=True)
class EscalatedDeliveryPolicy:
    in_quiet: bool
    urgent: bool
    allow_holder_shorten: bool
    allow_high_push: bool
    use_quiet_offer_expiry: bool


def effective_flip_at(
    slot_local: dt.datetime,
    escalation_lead_hours: int,
    quiet_start: dt.time,
    quiet_end: dt.time,
) -> dt.datetime:
    """Nominal slot−lead; clamp to quiet_start−30m when nominal lands in quiet (B5)."""
    nominal = slot_local - dt.timedelta(hours=escalation_lead_hours)
    if is_quiet_hours(nominal, quiet_start, quiet_end):
        anchor = preceding_quiet_start(nominal, quiet_start)
        return anchor - dt.timedelta(minutes=30)
    return nominal


def escalated_delivery_policy(
    now_local: dt.datetime,
    *,
    quiet_start: dt.time,
    quiet_end: dt.time,
    dispatch_deadline: dt.datetime | None,
) -> EscalatedDeliveryPolicy:
    """Single policy for flip, expand, notify, and born-escalated inserts."""
    in_quiet = is_quiet_hours(now_local, quiet_start, quiet_end)
    urgent = False
    if dispatch_deadline is not None:
        dl = dispatch_deadline
        if dl.tzinfo is None and now_local.tzinfo is not None:
            dl = dl.replace(tzinfo=now_local.tzinfo)
        elif dl.tzinfo is not None and now_local.tzinfo is not None:
            dl = dl.astimezone(now_local.tzinfo)
        next_end = next_quiet_end_on_or_after(now_local, quiet_end)
        urgent = dl <= next_end

    if not in_quiet:
        return EscalatedDeliveryPolicy(
            in_quiet=False,
            urgent=urgent,
            allow_holder_shorten=True,
            allow_high_push=True,
            use_quiet_offer_expiry=False,
        )
    if urgent:
        return EscalatedDeliveryPolicy(
            in_quiet=True,
            urgent=True,
            allow_holder_shorten=True,
            allow_high_push=True,
            use_quiet_offer_expiry=False,
        )
    return EscalatedDeliveryPolicy(
        in_quiet=True,
        urgent=False,
        allow_holder_shorten=False,
        allow_high_push=False,
        use_quiet_offer_expiry=True,
    )


def compute_escalated_offer_expires_at(
    now_local: dt.datetime,
    policy: EscalatedDeliveryPolicy,
    *,
    quiet_end: dt.time,
    escalated_ttl_seconds: int,
    dispatch_deadline: dt.datetime | None,
) -> dt.datetime:
    """Expiry for new escalated offers — capped by dispatch_deadline always."""
    if policy.use_quiet_offer_expiry:
        quiet_end_dt = next_quiet_end_on_or_after(now_local, quiet_end)
        candidate = quiet_end_dt + dt.timedelta(seconds=escalated_ttl_seconds)
    else:
        candidate = now_local + dt.timedelta(seconds=escalated_ttl_seconds)

    if dispatch_deadline is None:
        return candidate
    dl = dispatch_deadline
    if dl.tzinfo is None and now_local.tzinfo is not None:
        dl = dl.replace(tzinfo=now_local.tzinfo)
    elif dl.tzinfo is not None and now_local.tzinfo is not None:
        dl = dl.astimezone(now_local.tzinfo)
    return min(candidate, dl)


def dedupe_ttl_seconds_until_slot(slot_local: dt.datetime, now_local: dt.datetime) -> int:
    """Redis SETNX TTL for escalated high dedupe — until slot time."""
    delta = (slot_local - now_local).total_seconds()
    return max(60, int(delta))