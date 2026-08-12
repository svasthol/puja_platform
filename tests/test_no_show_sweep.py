"""P-SWEEP-CONFIRMED — stuck confirmed alert-only sweep (Phase 5, Option B)."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from app.monitoring.scanner import run_stuck_state_monitor
from app.workers.sweep import get_connection

CUSTOMER = "aaaaaaaa-0000-0000-0000-000000000001"
PUJARI_USER = "bbbbbbbb-0000-0000-0000-000000000001"
ADDRESS = "dddddddd-0000-0000-0000-000000000001"
PUJA = "11111111-1111-1111-1111-111111111111"

pytestmark = pytest.mark.asyncio


async def _pujari_id(session) -> str:
    return str(
        (
            await session.execute(
                text("SELECT id FROM pujaris WHERE user_id = :uid"),
                {"uid": PUJARI_USER},
            )
        ).scalar_one()
    )


def _unique_slot_time(uniq) -> str:
    h = (int(uniq.id().replace("-", "")[:4], 16) % 12) + 8
    m = int(uniq.id().replace("-", "")[4:8], 16) % 60
    return f"{h:02d}:{m:02d}:00"


@pytest.fixture(autouse=True)
async def _clear_pujari_stuck_bookings(session, seed):
    pid = await _pujari_id(session)
    await session.execute(
        text(
            """
            UPDATE bookings
            SET pujari_id = NULL, intended_pujari_id = NULL, updated_at = now()
            WHERE pujari_id = :pid AND cancelled_at IS NULL
            """
        ),
        {"pid": pid},
    )
    await session.commit()


async def _insert_stuck_confirmed(session, uniq) -> str:
    pid = await _pujari_id(session)
    slot_time = _unique_slot_time(uniq)
    bid = uniq.id()
    await session.execute(
        text(
            """
            INSERT INTO bookings (
                id, user_id, pujari_id, intended_pujari_id, puja_id, address_id, status_id,
                cancellation_policy_id, scheduled_date, scheduled_time, duration_minutes,
                total_amount, amount_due_online, amount_due_offline, payment_mode, paid_at,
                dispatch_mode, booking_class, created_at, updated_at
            )
            SELECT
                :bid, :uid, :pid, :pid, :puja, :addr, st.id,
                (SELECT id FROM cancellation_policies WHERE name='standard'),
                CURRENT_DATE - INTERVAL '2 days', CAST(:t AS time), 90,
                2100, 2100, 0, 'full_online', now(),
                'broadcast', 'advance', now(), now()
            FROM status_types st
            WHERE st.domain = 'booking' AND st.code = 'confirmed'
            """
        ),
        {
            "bid": bid,
            "uid": CUSTOMER,
            "pid": pid,
            "puja": PUJA,
            "addr": ADDRESS,
            "t": slot_time,
        },
    )
    await session.commit()
    return bid


async def test_stuck_confirmed_flags_ops_alert(session, seed, uniq):
    bid = await _insert_stuck_confirmed(session, uniq)

    conn = get_connection()
    try:
        summary = run_stuck_state_monitor(conn)
        alerted = summary["stuck_confirmed_no_show"]
    finally:
        conn.close()

    assert bid in alerted

    async with session.begin():
        row = (
            await session.execute(
                text(
                    "SELECT ops_alert_sent_at IS NOT NULL AS alerted "
                    "FROM booking_no_show_alerts WHERE booking_id = :bid"
                ),
                {"bid": bid},
            )
        ).scalar_one()
    assert row is True

    conn = get_connection()
    try:
        second = run_stuck_state_monitor(conn)
        assert bid not in second["stuck_confirmed_no_show"]
    finally:
        conn.close()


async def test_stuck_confirmed_skips_in_progress(session, seed, uniq):
    bid = await _insert_stuck_confirmed(session, uniq)
    in_progress_id = (
        await session.execute(
            text("SELECT id FROM status_types WHERE domain='booking' AND code='in_progress'")
        )
    ).scalar_one()
    await session.execute(
        text("UPDATE bookings SET status_id = :sid WHERE id = :bid"),
        {"sid": in_progress_id, "bid": bid},
    )
    await session.commit()

    conn = get_connection()
    try:
        summary = run_stuck_state_monitor(conn)
        alerted = summary["stuck_confirmed_no_show"]
    finally:
        conn.close()

    assert bid not in alerted
