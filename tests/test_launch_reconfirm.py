"""P-LAUNCH-RECONFIRM — advance attendance ping + RM escalation (§21.7)."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import text

from app.services.fcm_client import FcmOutcome, FcmResult
from app.workers.notifications import _notify_reconfirm_ping_impl
from app.workers.reconfirmation import (
    process_reconfirm_escalations,
    process_reconfirm_pings,
)
from app.workers.sweep import get_connection

CUSTOMER = "aaaaaaaa-0000-0000-0000-000000000001"
PUJARI = "cccccccc-0000-0000-0000-000000000001"
PUJARI2 = "cccccccc-0000-0000-0000-000000000002"
PUJARI_USER = "bbbbbbbb-0000-0000-0000-000000000001"
PUJARI_USER2 = "bbbbbbbb-0000-0000-0000-000000000002"
ADDRESS = "dddddddd-0000-0000-0000-000000000001"
PUJA = "11111111-1111-1111-1111-111111111111"


@pytest.fixture(autouse=True)
async def _clear_near_term_pujari_bookings(session):
    """Avoid ex_bookings_pujari_no_overlap collisions across reruns."""
    p1 = await _pujari_id(session, PUJARI_USER)
    p2 = await _pujari_id(session, PUJARI_USER2)
    await session.execute(
        text(
            """
            UPDATE bookings SET cancelled_at = now(), updated_at = now()
            WHERE pujari_id = ANY(:pids)
              AND cancelled_at IS NULL
              AND scheduled_date <= CURRENT_DATE + INTERVAL '3 days'
            """
        ),
        {"pids": [p1, p2]},
    )
    await session.commit()


def _unique_slot_time(uniq) -> str:
    h = (int(uniq.id().replace("-", "")[:4], 16) % 12) + 8
    m = int(uniq.id().replace("-", "")[4:8], 16) % 60
    return f"{h:02d}:{m:02d}:00"


def _slot_offset_hours(hours: int, uniq, *, max_extra_minutes: int = 90) -> str:
    """Relative slot offset; keep total under 24h when hours is the ping lead."""
    extra = int(uniq.id().replace("-", "")[:8], 16) % max_extra_minutes
    return f"{hours} hours {extra} minutes"


async def _pujari_id(session, user_id: str) -> str:
    return (
        await session.execute(
            text("SELECT id::text FROM pujaris WHERE user_id = :u"),
            {"u": user_id},
        )
    ).scalar_one()


async def _insert_confirmed_booking(
    session,
    uniq,
    *,
    slot_offset: str | None = None,
    confirmed_offset: str,
    pujari_id: str = PUJARI,
    scheduled_date: str | None = None,
    scheduled_time: str | None = None,
) -> str:
    """Insert confirmed booking; use slot_offset OR explicit date/time."""
    bid = uniq.id()
    if pujari_id == PUJARI:
        pujari_id = await _pujari_id(session, PUJARI_USER)
    elif pujari_id == PUJARI2:
        pujari_id = await _pujari_id(session, PUJARI_USER2)
    if slot_offset is not None:
        sched_date_expr = "(timezone('Asia/Kolkata', now()) + CAST(:slot_off AS interval))::date"
        sched_time_expr = "(timezone('Asia/Kolkata', now()) + CAST(:slot_off AS interval))::time"
        params = {
            "bid": bid,
            "uid": CUSTOMER,
            "pid": pujari_id,
            "puja": PUJA,
            "addr": ADDRESS,
            "slot_off": slot_offset,
        }
    else:
        sched_date_expr = "CAST(:sched_date AS date)"
        sched_time_expr = "CAST(:sched_time AS time)"
        params = {
            "bid": bid,
            "uid": CUSTOMER,
            "pid": pujari_id,
            "puja": PUJA,
            "addr": ADDRESS,
            "sched_date": scheduled_date or uniq.date,
            "sched_time": scheduled_time or _unique_slot_time(uniq),
        }
    await session.execute(
        text(
            f"""
            INSERT INTO bookings (
                id, user_id, pujari_id, puja_id, address_id, status_id,
                cancellation_policy_id, scheduled_date, scheduled_time,
                duration_minutes, total_amount, amount_due_online, amount_due_offline,
                payment_mode, paid_at, dispatch_mode, booking_class, created_at, updated_at
            )
            SELECT
                :bid,
                :uid,
                :pid,
                :puja,
                :addr,
                st.id,
                (SELECT id FROM cancellation_policies WHERE name='standard'),
                {sched_date_expr},
                {sched_time_expr},
                90, 2100, 2100, 0, 'full_online', now(), 'broadcast', 'advance',
                now(), now()
            FROM status_types st
            WHERE st.domain = 'booking' AND st.code = 'confirmed'
            """
        ),
        params,
    )
    confirmed_id = (
        await session.execute(
            text(
                "SELECT id FROM status_types WHERE domain='booking' AND code='confirmed'"
            )
        )
    ).scalar_one()
    await session.execute(
        text(
            """
            INSERT INTO booking_status_history (booking_id, status_id, changed_at)
            VALUES (:bid, :sid, now() + CAST(:conf_off AS interval))
            """
        ),
        {"bid": bid, "sid": confirmed_id, "conf_off": confirmed_offset},
    )
    await session.commit()
    return bid


@pytest.mark.asyncio
async def test_reconfirm_ping_sent_for_advance_booking(session, seed, uniq):
    bid = await _insert_confirmed_booking(
        session,
        uniq,
        slot_offset=_slot_offset_hours(22, uniq),
        confirmed_offset="-48 hours",
        pujari_id=PUJARI,
    )
    await session.execute(
        text(
            "INSERT INTO devices (id, user_id, device_token, platform, created_at) "
            "VALUES (gen_random_uuid(), :uid, :tok, 'android', now()) "
            "ON CONFLICT (device_token) DO NOTHING"
        ),
        {"uid": PUJARI_USER, "tok": f"tok-{uniq.id()}"},
    )
    await session.commit()

    conn = get_connection()
    try:
        with patch(
            "app.workers.notifications.send_push_sync",
            return_value=FcmResult(outcome=FcmOutcome.SENT),
        ):
            pinged = process_reconfirm_pings(conn)
        assert bid in pinged
        with conn.cursor() as cur:
            cur.execute(
                "SELECT ping_sent_at, rm_alert_sent_at FROM booking_reconfirmations "
                "WHERE booking_id = %s",
                (bid,),
            )
            row = cur.fetchone()
        assert row is not None
        assert row[0] is not None
        assert row[1] is None
    finally:
        conn.close()
    await session.execute(
        text("UPDATE bookings SET cancelled_at = now() WHERE id = :bid"),
        {"bid": bid},
    )
    await session.commit()


@pytest.mark.asyncio
async def test_reconfirm_skips_instant_lead_booking(session, seed, uniq):
    bid = await _insert_confirmed_booking(
        session,
        uniq,
        slot_offset=_slot_offset_hours(5, uniq),
        confirmed_offset="-2 hours",
        pujari_id=PUJARI2,
    )
    conn = get_connection()
    try:
        pinged = process_reconfirm_pings(conn)
        assert bid not in pinged
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM booking_reconfirmations WHERE booking_id = %s",
                (bid,),
            )
            count = cur.fetchone()[0]
        assert count == 0
    finally:
        conn.close()
    await session.execute(
        text("UPDATE bookings SET cancelled_at = now() WHERE id = :bid"),
        {"bid": bid},
    )
    await session.commit()


@pytest.mark.asyncio
async def test_reconfirm_escalation_after_four_hours(session, seed, uniq):
    bid = await _insert_confirmed_booking(
        session,
        uniq,
        confirmed_offset="-48 hours",
        pujari_id=PUJARI2,
        scheduled_date=uniq.date2,
        scheduled_time=_unique_slot_time(uniq),
    )
    await session.execute(
        text(
            """
            INSERT INTO booking_reconfirmations (booking_id, ping_sent_at)
            VALUES (:bid, now() - interval '1 day')
            """
        ),
        {"bid": bid},
    )
    rm_phone = f"+9198{uniq.id().replace('-', '')[:8]}"
    await session.execute(
        text(
            """
            INSERT INTO relationship_managers (id, name, phone, is_active)
            VALUES (gen_random_uuid(), 'Esc RM', :ph, true)
            """
        ),
        {"ph": rm_phone},
    )
    rm_id = (
        await session.execute(
            text("SELECT id FROM relationship_managers WHERE phone = :ph"),
            {"ph": rm_phone},
        )
    ).scalar_one()
    await session.execute(
        text("UPDATE bookings SET relationship_manager_id = :rm WHERE id = :bid"),
        {"rm": str(rm_id), "bid": bid},
    )
    await session.commit()

    conn = get_connection()
    try:
        with patch(
            "app.workers.notifications.send_transactional_sms_sync",
            return_value=True,
        ) as mock_sms:
            escalated = process_reconfirm_escalations(conn)
        assert bid in escalated
        assert mock_sms.called
        with conn.cursor() as cur:
            cur.execute(
                "SELECT rm_alert_sent_at FROM booking_reconfirmations WHERE booking_id = %s",
                (bid,),
            )
            row = cur.fetchone()
        assert row[0] is not None
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_notify_reconfirm_ping_writes_notification(session, seed, uniq):
    bid = await _insert_confirmed_booking(
        session,
        uniq,
        confirmed_offset="-48 hours",
        pujari_id=PUJARI,
        scheduled_date=uniq.date2,
        scheduled_time=_unique_slot_time(uniq),
    )
    with patch(
        "app.workers.notifications.send_push_sync",
        return_value=FcmResult(outcome=FcmOutcome.SKIPPED),
    ), patch(
        "app.workers.notifications.send_transactional_sms_sync",
        return_value=True,
    ):
        result = _notify_reconfirm_ping_impl(bid)
    assert result.get("sms") is True
