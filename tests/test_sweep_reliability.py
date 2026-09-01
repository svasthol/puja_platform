"""Sweep reliability — deadline exhaust, heartbeat, booking gates (P-SWEEP-RELIABILITY)."""
from __future__ import annotations

import datetime as dt

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.services.booking_gate import (
    BookingGateSettings,
    assert_booking_gate,
    past_slot_error_code,
)
from app.workers.sweep import exhaust_past_dispatch_deadline, get_connection
from app.workers.sweep_heartbeat import SWEEP_WORKER_NAME, record_worker_heartbeat, sweep_age_seconds

CUSTOMER = "aaaaaaaa-0000-0000-0000-000000000001"
PUJA = "11111111-1111-1111-1111-111111111111"
ADDRESS = "dddddddd-0000-0000-0000-000000000001"


def _unique_slot_time(uniq) -> str:
    h = (int(uniq.id().replace("-", "")[:4], 16) % 12) + 8
    m = int(uniq.id().replace("-", "")[4:8], 16) % 60
    return f"{h:02d}:{m:02d}:00"


def test_past_slot_error_code():
    assert past_slot_error_code(0.0) == "SLOT_IN_PAST"
    assert past_slot_error_code(-1.5) == "SLOT_IN_PAST"
    assert past_slot_error_code(0.01) is None


def test_assert_booking_gate_past_slot_raises():
    settings = BookingGateSettings(instant_lead_hours=4, night_bookings_enabled=False)
    now = dt.datetime(2036, 6, 15, 14, 0, tzinfo=dt.UTC)
    with pytest.raises(HTTPException) as exc:
        assert_booking_gate(dt.date(2036, 6, 15), dt.time(10, 0), settings, now=now)
    assert exc.value.detail["code"] == "SLOT_IN_PAST"


@pytest.mark.asyncio
async def test_sweep_exhaust_past_deadline_batch(session, seed, uniq):
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

        exhausted = exhaust_past_dispatch_deadline(conn)
        assert bid in exhausted

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT st.code FROM bookings b
                JOIN status_types st ON st.id = b.status_id
                WHERE b.id = %s
                """,
                (bid,),
            )
            assert cur.fetchone()[0] == "failed_no_pujari"
    finally:
        conn.close()


def test_sweep_heartbeat_record_and_age(uniq):
    conn = get_connection()
    try:
        record_worker_heartbeat(conn, SWEEP_WORKER_NAME, {"test": True, "booking": uniq.id()})
        age = sweep_age_seconds(conn)
        assert age is not None
        assert age < 5.0
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_assert_slot_not_past_for_accept(session, seed, uniq):
    from app.services.slot_guard import assert_slot_not_past_for_accept

    bid = uniq.id()
    now = dt.datetime.now(dt.UTC)
    past_date = (now - dt.timedelta(days=30)).date()
    slot_time = _unique_slot_time(uniq)
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
                :sd, CAST(:st AS time), 90, 2100, 2100, 0, 'full_online', now(),
                'broadcast', 'instant', now(), now()
            )
            """
        ),
        {
            "bid": bid,
            "uid": "aaaaaaaa-0000-0000-0000-000000000002",
            "puja": PUJA,
            "addr": ADDRESS,
            "sd": past_date,
            "st": slot_time,
        },
    )
    await session.commit()

    with pytest.raises(HTTPException) as exc:
        await assert_slot_not_past_for_accept(
            session, booking_id=__import__("uuid").UUID(bid)
        )
    assert exc.value.status_code == 410
