"""Launch-gate: sweep step 2 releases ONLY the hold linked to the abandoned booking."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from app.workers.dispatch import broadcast_booking, rebroadcast_booking
from app.workers.sweep import (
    abandon_stale_payment_pending,
    bookings_needing_initial_broadcast,
    bookings_needing_rebroadcast,
    get_connection,
)

from tests.test_inbox_cap import (
    _clear_presence,
    _ensure_pujari_dispatch_ready,
    _insert_broadcast_target,
    _pujari_ids,
    _require_migration_014,
    _set_presence,
    _unique_slot_time,
)


@pytest.mark.asyncio
async def test_only_linked_hold_released(session, seed, uniq):
    h1, h2, bk = uniq.id(), uniq.id(), uniq.id()
    async with session.begin():
        await session.execute(text(
            "INSERT INTO slot_holds (id,user_id,pujari_id,slot_date,slot_time,held_at,expires_at) VALUES "
            "(:h1,'aaaaaaaa-0000-0000-0000-000000000001','cccccccc-0000-0000-0000-000000000001',"
            ":d1,'09:00',now(),now()+interval '15 min'),"
            "(:h2,'aaaaaaaa-0000-0000-0000-000000000001','cccccccc-0000-0000-0000-000000000002',"
            ":d2,'09:00',now(),now()+interval '15 min')"),
            {"h1": h1, "h2": h2, "d1": uniq.date, "d2": uniq.date2})
        await session.execute(text(
            "INSERT INTO bookings (id,user_id,puja_id,address_id,status_id,cancellation_policy_id,"
            "scheduled_date,scheduled_time,duration_minutes,total_amount,amount_due_online,"
            "amount_due_offline,payment_mode,hold_id,created_at,updated_at) VALUES (:bk,"
            "'aaaaaaaa-0000-0000-0000-000000000001','11111111-1111-1111-1111-111111111111',"
            "'dddddddd-0000-0000-0000-000000000001',"
            "(SELECT id FROM status_types WHERE domain='booking' AND code='payment_pending'),"
            "(SELECT id FROM cancellation_policies WHERE name='standard'),:d1,'09:00',90,"
            "2100,2100,0,'full_online',:h1, now()-interval '20 min', now()-interval '20 min')"),
            {"bk": bk, "h1": h1, "d1": uniq.date})

    conn = get_connection()
    try:
        abandon_stale_payment_pending(conn)
    finally:
        conn.close()

    async with session.begin():
        rows = dict((str(r[0]), r[1]) for r in (await session.execute(text(
            "SELECT id, released_at IS NULL FROM slot_holds WHERE id IN (:h1,:h2)"),
            {"h1": h1, "h2": h2})).all())
    assert rows[h1] is False   # linked hold released
    assert rows[h2] is True    # unrelated hold survives


def test_stranded_rebroadcast_after_zero_offer_round(uniq):
    """DISPATCH_FLOW §4: zero-offer rounds must retry without a prior assignment row."""
    conn = get_connection()
    bid = uniq.id()
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
                    %s, 'aaaaaaaa-0000-0000-0000-000000000001',
                    '11111111-1111-1111-1111-111111111111',
                    'dddddddd-0000-0000-0000-000000000001',
                    (SELECT id FROM status_types WHERE domain='booking' AND code='requested'),
                    (SELECT id FROM cancellation_policies WHERE name='standard'),
                    %s, %s::time, 90, 2100, 2100, 0, 'full_online', now(),
                    'broadcast', 'advance', now(), now()
                )
                """,
                (bid, uniq.date, slot_time),
            )
            cur.execute(
                """
                INSERT INTO booking_dispatch_state (
                    booking_id, round, last_dispatched, dispatch_starts_at, dispatch_deadline
                ) VALUES (%s, 1, now(), now() - interval '1 minute', now() + interval '2 hours')
                """,
                (bid,),
            )
        conn.commit()

        stranded = bookings_needing_rebroadcast(conn)
        assert bid in stranded
    finally:
        conn.close()


def test_stranded_rebroadcast_excludes_live_offer(uniq):
    conn = get_connection()
    bid = uniq.id()
    slot_time = _unique_slot_time(uniq)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM pujaris WHERE user_id = 'bbbbbbbb-0000-0000-0000-000000000001'"
            )
            pujari_row = cur.fetchone()
            assert pujari_row is not None
            pujari_id = pujari_row[0]
            cur.execute(
                """
                INSERT INTO bookings (
                    id, user_id, puja_id, address_id, status_id, cancellation_policy_id,
                    scheduled_date, scheduled_time, duration_minutes, total_amount,
                    amount_due_online, amount_due_offline, payment_mode, paid_at,
                    dispatch_mode, booking_class, created_at, updated_at
                ) VALUES (
                    %s, 'aaaaaaaa-0000-0000-0000-000000000001',
                    '11111111-1111-1111-1111-111111111111',
                    'dddddddd-0000-0000-0000-000000000001',
                    (SELECT id FROM status_types WHERE domain='booking' AND code='requested'),
                    (SELECT id FROM cancellation_policies WHERE name='standard'),
                    %s, %s::time, 90, 2100, 2100, 0, 'full_online', now(),
                    'broadcast', 'advance', now(), now()
                )
                """,
                (bid, uniq.date, slot_time),
            )
            cur.execute(
                """
                INSERT INTO booking_dispatch_state (
                    booking_id, round, last_dispatched, dispatch_starts_at, dispatch_deadline
                ) VALUES (%s, 1, now(), now() - interval '1 minute', now() + interval '2 hours')
                """,
                (bid,),
            )
            cur.execute(
                """
                INSERT INTO booking_assignments (
                    id, booking_id, pujari_id, status_id, offered_at, expires_at
                ) VALUES (
                    gen_random_uuid(), %s, %s,
                    (SELECT id FROM status_types WHERE domain='assignment' AND code='offered'),
                    now(), now() + interval '24 hours'
                )
                """,
                (bid, pujari_id),
            )
        conn.commit()

        assert bid not in bookings_needing_rebroadcast(conn)
    finally:
        conn.close()


def test_stranded_rebroadcast_excludes_exhausted(uniq):
    conn = get_connection()
    bid = uniq.id()
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
                    %s, 'aaaaaaaa-0000-0000-0000-000000000001',
                    '11111111-1111-1111-1111-111111111111',
                    'dddddddd-0000-0000-0000-000000000001',
                    (SELECT id FROM status_types WHERE domain='booking' AND code='requested'),
                    (SELECT id FROM cancellation_policies WHERE name='standard'),
                    %s, %s::time, 90, 2100, 2100, 0, 'full_online', now(),
                    'broadcast', 'advance', now(), now()
                )
                """,
                (bid, uniq.date, slot_time),
            )
            cur.execute(
                """
                INSERT INTO booking_dispatch_state (
                    booking_id, round, last_dispatched, exhausted_at,
                    dispatch_starts_at, dispatch_deadline
                ) VALUES (%s, 5, now(), now(), now() - interval '1 hour', now() - interval '30 minutes')
                """,
                (bid,),
            )
        conn.commit()

        assert bid not in bookings_needing_rebroadcast(conn)
    finally:
        conn.close()


def test_initial_broadcast_paid_without_dispatch_row(uniq):
    conn = get_connection()
    bid = uniq.id()
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
                    %s, 'aaaaaaaa-0000-0000-0000-000000000001',
                    '11111111-1111-1111-1111-111111111111',
                    'dddddddd-0000-0000-0000-000000000001',
                    (SELECT id FROM status_types WHERE domain='booking' AND code='requested'),
                    (SELECT id FROM cancellation_policies WHERE name='standard'),
                    %s, %s::time, 90, 2100, 2100, 0, 'full_online', now(),
                    'broadcast', 'advance', now(), now()
                )
                """,
                (bid, uniq.date, slot_time),
            )
        conn.commit()

        pending = bookings_needing_initial_broadcast(conn)
        assert bid in pending
        assert bid not in bookings_needing_rebroadcast(conn)
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_zero_offer_round_retries_when_pujari_comes_online(session, seed, uniq):
    """End-to-end: offline dispatch -> sweep stranded -> online rebroadcast creates offer."""
    await _require_migration_014(session)
    pujari1, pujari2 = await _pujari_ids(session)
    pujari1, pujari2 = await _ensure_pujari_dispatch_ready(session)

    bid = uniq.id()
    slot_time = _unique_slot_time(uniq)
    await _insert_broadcast_target(
        session,
        booking_id=bid,
        slot_date=uniq.date,
        slot_time=slot_time,
        booking_class="advance",
    )
    await session.commit()

    _clear_presence(pujari1, pujari2)
    result = broadcast_booking(bid)
    assert result.get("offers") == 0

    conn = get_connection()
    try:
        assert bid in bookings_needing_rebroadcast(conn)
    finally:
        conn.close()

    _set_presence(pujari1, pujari2)
    retry = rebroadcast_booking(bid)
    assert retry.get("offers", 0) >= 1

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM booking_assignments WHERE booking_id = %s",
                (bid,),
            )
            assert cur.fetchone()[0] >= 1
    finally:
        conn.close()
