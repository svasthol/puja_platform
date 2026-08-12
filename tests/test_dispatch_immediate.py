"""DV2-IMMEDIATE — worker-owned dispatch state + immediate advance start (§21.6.C)."""
from __future__ import annotations

import datetime as dt
import uuid
import zoneinfo

import pytest
from sqlalchemy import text

from app.services import booking_events, webhook_service
from app.services.dispatch_launch import (
    LaunchDispatchSettings,
    compute_dispatch_windows,
    offer_expires_interval,
    slot_datetime,
)
from app.workers.dispatch import broadcast_booking
from app.workers.sweep import get_connection

CUSTOMER = "aaaaaaaa-0000-0000-0000-000000000001"
PUJA = "11111111-1111-1111-1111-111111111111"
ADDRESS = "dddddddd-0000-0000-0000-000000000001"
_TZ = zoneinfo.ZoneInfo("Asia/Kolkata")


async def _require_migration_014(session) -> None:
    row = (
        await session.execute(
            text(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'bookings'
                  AND column_name = 'booking_class'
                """
            )
        )
    ).scalar_one_or_none()
    if row is None:
        pytest.skip("migration_014 not applied — run: python scripts/apply_migration_014.py")


def test_offer_expires_interval_by_class():
    settings = LaunchDispatchSettings()
    assert offer_expires_interval("instant", settings) == "120 seconds"
    assert offer_expires_interval("advance", settings) == "24 hours"


def test_instant_deadline_not_slot_minus_three_hours():
    """Instant bookings must not inherit advance fail deadline (§21.6.C)."""
    settings = LaunchDispatchSettings()
    now = dt.datetime(2026, 7, 21, 10, 0, tzinfo=_TZ)
    _, deadline = compute_dispatch_windows(
        dt.date(2026, 7, 21),
        dt.time(12, 0),
        settings,
        booking_class="instant",
        now=now,
    )
    assert deadline == now + dt.timedelta(minutes=30)
    assert deadline != slot_datetime(dt.date(2026, 7, 21), dt.time(12, 0)) - dt.timedelta(
        hours=3
    )


def _unique_slot_time(uniq) -> str:
    h = (int(uniq.id().replace("-", "")[:4], 16) % 12) + 8
    m = int(uniq.id().replace("-", "")[4:8], 16) % 60
    return f"{h:02d}:{m:02d}:00"


@pytest.mark.asyncio
async def test_webhook_does_not_write_dispatch_state(session, seed, uniq, monkeypatch):
    """Webhook enqueues broadcast only; worker creates booking_dispatch_state."""
    await _require_migration_014(session)

    booking_id = uuid.uuid4()
    now = dt.datetime.now(dt.UTC)
    slot_time = _unique_slot_time(uniq)
    pending_id = (
        await session.execute(
            text(
                "SELECT id FROM status_types WHERE domain='booking' AND code='payment_pending'"
            )
        )
    ).scalar_one()
    policy_id = (
        await session.execute(
            text("SELECT id FROM cancellation_policies WHERE name='standard'")
        )
    ).scalar_one()

    await session.execute(
        text(
            """
            INSERT INTO bookings (
                id, user_id, puja_id, address_id, status_id, cancellation_policy_id,
                scheduled_date, scheduled_time, duration_minutes, total_amount,
                amount_due_online, amount_due_offline, payment_mode, dispatch_mode,
                booking_class, created_at, updated_at
            ) VALUES (
                :bid, :uid, :puja, :addr, :sid, :cpid,
                :sd, CAST(:st AS time), 90, 2100, 2100, 0, 'full_online', 'broadcast',
                'advance', :now, :now
            )
            """
        ),
        {
            "bid": str(booking_id),
            "uid": CUSTOMER,
            "puja": PUJA,
            "addr": ADDRESS,
            "sid": pending_id,
            "cpid": policy_id,
            "sd": dt.date.fromisoformat(uniq.date),
            "st": slot_time,
            "now": now,
        },
    )
    await session.commit()

    async def _noop_publish(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(booking_events, "publish_booking_event", _noop_publish)

    result = await webhook_service.handle_payment_captured(
        session,
        booking_id=booking_id,
        gateway_txn_id=f"pay_{uniq.id()}",
        idempotency_key=f"idem_{uniq.id()}",
        amount_paise=210000,
    )
    await session.commit()

    assert result.get("enqueue_broadcast") == str(booking_id)
    state_count = (
        await session.execute(
            text("SELECT count(*) FROM booking_dispatch_state WHERE booking_id = :bid"),
            {"bid": str(booking_id)},
        )
    ).scalar_one()
    assert state_count == 0


def test_worker_sets_immediate_advance_windows(uniq):
    """First broadcast creates state row with dispatch_starts_at=now() for advance."""
    conn = get_connection()
    bid = uniq.id()
    slot_date = uniq.date
    slot_time = _unique_slot_time(uniq)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bookings (
                    id, user_id, puja_id, address_id, status_id, cancellation_policy_id,
                    scheduled_date, scheduled_time, duration_minutes, total_amount,
                    amount_due_online, amount_due_offline, payment_mode, paid_at,
                    dispatch_mode, booking_class, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s,
                    (SELECT id FROM status_types WHERE domain='booking' AND code='requested'),
                    (SELECT id FROM cancellation_policies WHERE name='standard'),
                    %s, %s::time, 90, 2100, 2100, 0, 'full_online', now(), 'broadcast',
                    'advance', now(), now()
                )
                """,
                (bid, CUSTOMER, PUJA, ADDRESS, slot_date, slot_time),
            )
        conn.commit()

        result = broadcast_booking(bid)
        assert result.get("skipped") != "deferred"

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT dispatch_starts_at, dispatch_deadline
                FROM booking_dispatch_state WHERE booking_id = %s
                """,
                (bid,),
            )
            starts_at, deadline = cur.fetchone()
            cur.execute("SELECT now()")
            now_db = cur.fetchone()[0]

        assert starts_at is not None
        assert deadline is not None
        assert abs((starts_at - now_db).total_seconds()) < 120
        hour, minute, _ = slot_time.split(":")
        expected_deadline = slot_datetime(
            dt.date.fromisoformat(slot_date), dt.time(int(hour), int(minute))
        ) - dt.timedelta(hours=3)
        assert abs((deadline - expected_deadline).total_seconds()) < 2
    finally:
        conn.close()


def test_worker_sets_instant_windows(uniq):
    """Instant class gets now()+30m deadline, not slot-3h."""
    conn = get_connection()
    bid = uniq.id()
    slot_date = uniq.date2
    slot_time = _unique_slot_time(uniq)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bookings (
                    id, user_id, puja_id, address_id, status_id, cancellation_policy_id,
                    scheduled_date, scheduled_time, duration_minutes, total_amount,
                    amount_due_online, amount_due_offline, payment_mode, paid_at,
                    dispatch_mode, booking_class, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s,
                    (SELECT id FROM status_types WHERE domain='booking' AND code='requested'),
                    (SELECT id FROM cancellation_policies WHERE name='standard'),
                    %s, %s::time, 90, 2100, 2100, 0, 'full_online', now(), 'broadcast',
                    'instant', now(), now()
                )
                """,
                (bid, CUSTOMER, PUJA, ADDRESS, slot_date, slot_time),
            )
        conn.commit()

        broadcast_booking(bid)

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT dispatch_starts_at, dispatch_deadline, now()
                FROM booking_dispatch_state, (SELECT now() AS now) n
                WHERE booking_id = %s
                """,
                (bid,),
            )
            starts_at, deadline, now_db = cur.fetchone()

        assert abs((starts_at - now_db).total_seconds()) < 120
        assert abs((deadline - (starts_at + dt.timedelta(minutes=30))).total_seconds()) < 2
    finally:
        conn.close()
