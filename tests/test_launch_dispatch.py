"""Launch dispatch + heartbeat (P-LAUNCH-DISPATCH, P-LAUNCH-HEARTBEAT)."""
from __future__ import annotations

import datetime as dt
import zoneinfo

import pytest
from sqlalchemy import text

from app.services.dispatch_launch import (
    LaunchDispatchSettings,
    compute_dispatch_windows,
    slot_datetime,
)
from app.workers.dispatch import broadcast_booking, exhaust_booking_no_pujari
from app.workers.sweep import get_connection

CUSTOMER = "aaaaaaaa-0000-0000-0000-000000000001"
PUJARI = "cccccccc-0000-0000-0000-000000000001"
PUJA = "11111111-1111-1111-1111-111111111111"
ADDRESS = "dddddddd-0000-0000-0000-000000000001"
_TZ = zoneinfo.ZoneInfo("Asia/Kolkata")


def _unique_slot_time(uniq) -> str:
    h = (int(uniq.id().replace("-", "")[:4], 16) % 12) + 8
    m = int(uniq.id().replace("-", "")[4:8], 16) % 60
    return f"{h:02d}:{m:02d}:00"


def test_compute_dispatch_windows_instant_vs_advance():
    settings = LaunchDispatchSettings()
    now = dt.datetime(2026, 7, 21, 10, 0, tzinfo=_TZ)

    instant_date = dt.date(2026, 7, 21)
    instant_time = dt.time(13, 0)
    starts, deadline = compute_dispatch_windows(
        instant_date, instant_time, settings, booking_class="instant", now=now
    )
    assert starts == now
    slot = slot_datetime(instant_date, instant_time)
    pre_slot = slot - dt.timedelta(minutes=settings.dispatch_buffer_minutes)
    assert deadline == max(now + dt.timedelta(minutes=30), pre_slot)

    advance_date = dt.date(2026, 7, 25)
    advance_time = dt.time(14, 0)
    starts, deadline = compute_dispatch_windows(
        advance_date, advance_time, settings, booking_class="advance", now=now
    )
    slot = slot_datetime(advance_date, advance_time)
    assert starts == now
    assert deadline == slot - dt.timedelta(hours=3)

    rollback = LaunchDispatchSettings(immediate_dispatch_on_payment=False)
    starts, deadline = compute_dispatch_windows(
        advance_date, advance_time, rollback, booking_class="advance", now=now
    )
    assert starts == slot - dt.timedelta(hours=4)
    assert deadline == slot - dt.timedelta(hours=3)


@pytest.mark.asyncio
async def test_dispatch_deferred_before_starts_at(session, seed, uniq):
    slot_time = _unique_slot_time(uniq)
    bid = uniq.id()
    await session.execute(
        text(
            """
            INSERT INTO bookings (
                id, user_id, puja_id, address_id, status_id, cancellation_policy_id,
                scheduled_date, scheduled_time, duration_minutes, total_amount,
                amount_due_online, amount_due_offline, payment_mode, paid_at,
                dispatch_mode, booking_class, created_at, updated_at
            ) VALUES (
                :bid, :uid, :puja, :addr,
                (SELECT id FROM status_types WHERE domain='booking' AND code='requested'),
                (SELECT id FROM cancellation_policies WHERE name='standard'),
                :d, CAST(:t AS time), 90, 2100, 2100, 0, 'full_online', now(), 'broadcast',
                'advance', now(), now()
            )
            """
        ),
        {"bid": bid, "uid": CUSTOMER, "puja": PUJA, "addr": ADDRESS, "d": uniq.date, "t": slot_time},
    )
    await session.execute(
        text(
            """
            INSERT INTO booking_dispatch_state (booking_id, dispatch_starts_at, dispatch_deadline)
            VALUES (:bid, now() + interval '2 hours', now() + interval '3 hours')
            """
        ),
        {"bid": bid},
    )
    await session.commit()

    result = broadcast_booking(bid)
    assert result.get("skipped") == "deferred"


@pytest.mark.asyncio
async def test_dispatch_exhausts_past_deadline(session, seed, uniq):
    slot_time = _unique_slot_time(uniq)
    bid = uniq.id()
    await session.execute(
        text(
            """
            INSERT INTO bookings (
                id, user_id, puja_id, address_id, status_id, cancellation_policy_id,
                scheduled_date, scheduled_time, duration_minutes, total_amount,
                amount_due_online, amount_due_offline, payment_mode, paid_at,
                dispatch_mode, booking_class, created_at, updated_at
            ) VALUES (
                :bid, :uid, :puja, :addr,
                (SELECT id FROM status_types WHERE domain='booking' AND code='requested'),
                (SELECT id FROM cancellation_policies WHERE name='standard'),
                :d, CAST(:t AS time), 90, 2100, 2100, 0, 'full_online', now(), 'broadcast',
                'advance', now(), now()
            )
            """
        ),
        {"bid": bid, "uid": CUSTOMER, "puja": PUJA, "addr": ADDRESS, "d": uniq.date, "t": slot_time},
    )
    await session.execute(
        text(
            """
            INSERT INTO booking_dispatch_state (booking_id, dispatch_starts_at, dispatch_deadline)
            VALUES (:bid, now() - interval '2 hours', now() - interval '1 minute')
            """
        ),
        {"bid": bid},
    )
    await session.commit()

    result = broadcast_booking(bid)
    assert result.get("status") == "failed_no_pujari"

    status_code = (
        await session.execute(
            text(
                """
                SELECT st.code FROM bookings b
                JOIN status_types st ON st.id = b.status_id
                WHERE b.id = :bid
                """
            ),
            {"bid": bid},
        )
    ).scalar_one()
    assert status_code == "failed_no_pujari"


def test_sweep_exhaust_past_deadline(uniq):
    conn = get_connection()
    slot_time = _unique_slot_time(uniq)
    try:
        bid = uniq.id()
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
                (bid, CUSTOMER, PUJA, ADDRESS, uniq.date, slot_time),
            )
            cur.execute(
                """
                INSERT INTO booking_dispatch_state (booking_id, dispatch_starts_at, dispatch_deadline)
                VALUES (%s, now() - interval '2 hours', now() - interval '1 minute')
                """,
                (bid,),
            )
        conn.commit()

        with conn.cursor() as cur:
            result = exhaust_booking_no_pujari(cur, conn, bid)
        assert result.get("status") == "failed_no_pujari"
    finally:
        conn.close()


def test_heartbeat_model_optional_gps():
    from app.api.v1.endpoints.pujaris import Heartbeat

    assert Heartbeat().lat is None
    assert Heartbeat().lng is None
    hb = Heartbeat(lat=17.4, lng=78.4)
    assert hb.lat == 17.4

    with pytest.raises(ValueError, match="together"):
        Heartbeat(lat=17.4)
