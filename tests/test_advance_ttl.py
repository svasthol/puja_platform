"""DV2-ADVANCE-TTL — sweep carve-out + refresh_advance_offers beat (§21.6.D)."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from app.workers.advance_offers import refresh_advance_offers
from app.workers.sweep import expire_stale_assignments, get_connection

CUSTOMER = "aaaaaaaa-0000-0000-0000-000000000001"
PUJA = "11111111-1111-1111-1111-111111111111"
ADDRESS = "dddddddd-0000-0000-0000-000000000001"
PUJARI_USER1 = "bbbbbbbb-0000-0000-0000-000000000001"


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


async def _pujari_id(session) -> str:
    return (
        await session.execute(
            text("SELECT id::text FROM pujaris WHERE user_id = :u"),
            {"u": PUJARI_USER1},
        )
    ).scalar_one()


async def _status_id(session, domain: str, code: str) -> int:
    return (
        await session.execute(
            text("SELECT id FROM status_types WHERE domain = :d AND code = :c"),
            {"d": domain, "c": code},
        )
    ).scalar_one()


async def _seed_booking_with_offer(
    session,
    *,
    booking_id: str,
    assignment_id: str,
    pujari_id: str,
    slot_date: str,
    slot_time: str,
    booking_class: str,
    expires_at_sql: str,
    dispatch_deadline_sql: str,
    urgency_escalated: bool = False,
) -> None:
    requested_id = await _status_id(session, "booking", "requested")
    offered_id = await _status_id(session, "assignment", "offered")
    policy_id = (
        await session.execute(
            text("SELECT id FROM cancellation_policies WHERE name = 'standard'")
        )
    ).scalar_one()

    await session.execute(
        text(
            f"""
            INSERT INTO bookings (
                id, user_id, puja_id, address_id, status_id, cancellation_policy_id,
                scheduled_date, scheduled_time, duration_minutes, total_amount,
                amount_due_online, amount_due_offline, payment_mode, paid_at,
                dispatch_mode, booking_class, created_at, updated_at
            ) VALUES (
                :bid, :uid, :puja, :addr, :sid, :cpid,
                :sd, CAST(:st AS time), 90, 2100, 2100, 0, 'full_online', now(),
                'broadcast', :cls, now(), now()
            )
            """
        ),
        {
            "bid": booking_id,
            "uid": CUSTOMER,
            "puja": PUJA,
            "addr": ADDRESS,
            "sid": requested_id,
            "cpid": policy_id,
            "sd": slot_date,
            "st": slot_time,
            "cls": booking_class,
        },
    )
    await session.execute(
        text(
            f"""
            INSERT INTO booking_dispatch_state (
                booking_id, dispatch_starts_at, dispatch_deadline, urgency_escalated_at
            ) VALUES (
                :bid, now() - interval '1 hour',
                {dispatch_deadline_sql},
                {'now()' if urgency_escalated else 'NULL'}
            )
            """
        ),
        {"bid": booking_id},
    )
    await session.execute(
        text(
            f"""
            INSERT INTO booking_assignments (
                id, booking_id, pujari_id, status_id, offered_at, expires_at
            ) VALUES (
                :aid, :bid, :pid, :offered,
                now() - interval '3 hours', {expires_at_sql}
            )
            """
        ),
        {
            "aid": assignment_id,
            "bid": booking_id,
            "pid": pujari_id,
            "offered": offered_id,
        },
    )


def _assignment_status(conn, assignment_id: str) -> tuple[str, bool]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT st.code, ba.responded_at IS NOT NULL
            FROM booking_assignments ba
            JOIN status_types st ON st.id = ba.status_id
            WHERE ba.id = %s
            """,
            (assignment_id,),
        )
        return cur.fetchone()


def _assignment_expires_at(conn, assignment_id: str):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT expires_at FROM booking_assignments WHERE id = %s",
            (assignment_id,),
        )
        return cur.fetchone()[0]


@pytest.mark.asyncio
async def test_sweep_carves_out_active_advance_offer(session, seed, uniq):
    """Past expires_at but inside dispatch window → sweep step 3 skips advance offer."""
    await _require_migration_014(session)
    pujari_id = await _pujari_id(session)
    bid, aid = uniq.id(), uniq.id()

    await _seed_booking_with_offer(
        session,
        booking_id=bid,
        assignment_id=aid,
        pujari_id=pujari_id,
        slot_date=uniq.date2,
        slot_time="11:00:00",
        booking_class="advance",
        expires_at_sql="now() - interval '1 minute'",
        dispatch_deadline_sql="now() + interval '48 hours'",
    )
    await session.commit()

    conn = get_connection()
    try:
        expired = expire_stale_assignments(conn)
    finally:
        conn.close()

    assert bid not in expired
    conn = get_connection()
    try:
        status, responded = _assignment_status(conn, aid)
    finally:
        conn.close()
    assert status == "offered"
    assert responded is False


@pytest.mark.asyncio
async def test_sweep_expires_instant_offer_past_ttl(session, seed, uniq):
    """Instant offers keep legacy step-3 expire → rebroadcast behaviour."""
    await _require_migration_014(session)
    pujari_id = await _pujari_id(session)
    bid, aid = uniq.id(), uniq.id()

    await _seed_booking_with_offer(
        session,
        booking_id=bid,
        assignment_id=aid,
        pujari_id=pujari_id,
        slot_date=uniq.date,
        slot_time="12:00:00",
        booking_class="instant",
        expires_at_sql="now() - interval '1 minute'",
        dispatch_deadline_sql="now() + interval '20 minutes'",
    )
    await session.commit()

    conn = get_connection()
    try:
        expired = expire_stale_assignments(conn)
    finally:
        conn.close()

    assert bid in expired
    conn = get_connection()
    try:
        status, responded = _assignment_status(conn, aid)
    finally:
        conn.close()
    assert status == "expired"
    assert responded is True


@pytest.mark.asyncio
async def test_sweep_expires_advance_offer_past_dispatch_deadline(session, seed, uniq):
    """Advance carve-out ends when dispatch_deadline passes."""
    await _require_migration_014(session)
    pujari_id = await _pujari_id(session)
    bid, aid = uniq.id(), uniq.id()

    await _seed_booking_with_offer(
        session,
        booking_id=bid,
        assignment_id=aid,
        pujari_id=pujari_id,
        slot_date=uniq.date2,
        slot_time="13:00:00",
        booking_class="advance",
        expires_at_sql="now() - interval '1 minute'",
        dispatch_deadline_sql="now() - interval '1 minute'",
    )
    await session.commit()

    conn = get_connection()
    try:
        expired = expire_stale_assignments(conn)
    finally:
        conn.close()

    assert bid in expired
    conn = get_connection()
    try:
        status, _ = _assignment_status(conn, aid)
    finally:
        conn.close()
    assert status == "expired"


@pytest.mark.asyncio
async def test_refresh_advance_offers_extends_expires_at(session, seed, uniq):
    """Refresh beat rolls expires_at forward in place (no new assignment row)."""
    await _require_migration_014(session)
    pujari_id = await _pujari_id(session)
    bid, aid = uniq.id(), uniq.id()

    await _seed_booking_with_offer(
        session,
        booking_id=bid,
        assignment_id=aid,
        pujari_id=pujari_id,
        slot_date=uniq.date2,
        slot_time="14:00:00",
        booking_class="advance",
        expires_at_sql="now() + interval '1 hour'",
        dispatch_deadline_sql="now() + interval '48 hours'",
    )
    await session.commit()

    conn = get_connection()
    try:
        before = _assignment_expires_at(conn, aid)
        refresh_advance_offers(conn)
        after = _assignment_expires_at(conn, aid)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM booking_assignments WHERE booking_id = %s",
                (bid,),
            )
            row_count = cur.fetchone()[0]
            cur.execute(
                "SELECT expires_at > now() + interval '20 hours' FROM booking_assignments WHERE id = %s",
                (aid,),
            )
            extended = cur.fetchone()[0]
    finally:
        conn.close()

    assert row_count == 1
    assert after > before
    assert extended is True


@pytest.mark.asyncio
async def test_lg_refresh_vs_accept_no_phantom_live_offer(session, seed, uniq):
    """Accept resolves the row; refresh must not resurrect a live offered assignment."""
    await _require_migration_014(session)
    pujari_id = await _pujari_id(session)
    bid, aid = uniq.id(), uniq.id()

    await _seed_booking_with_offer(
        session,
        booking_id=bid,
        assignment_id=aid,
        pujari_id=pujari_id,
        slot_date=uniq.date2,
        slot_time="15:00:00",
        booking_class="advance",
        expires_at_sql="now() + interval '1 hour'",
        dispatch_deadline_sql="now() + interval '48 hours'",
    )
    await session.execute(
        text(
            """
            UPDATE booking_assignments
            SET status_id = (
                    SELECT id FROM status_types
                    WHERE domain = 'assignment' AND code = 'accepted'
                ),
                responded_at = now()
            WHERE id = :aid
            """
        ),
        {"aid": aid},
    )
    await session.execute(
        text(
            """
            UPDATE bookings
            SET pujari_id = :pid,
                status_id = (
                    SELECT id FROM status_types
                    WHERE domain = 'booking' AND code = 'confirmed'
                )
            WHERE id = :bid
            """
        ),
        {"bid": bid, "pid": pujari_id},
    )
    await session.commit()

    conn = get_connection()
    try:
        before_expires = _assignment_expires_at(conn, aid)
        refresh_advance_offers(conn)
        status, responded = _assignment_status(conn, aid)
        after_expires = _assignment_expires_at(conn, aid)
    finally:
        conn.close()

    assert status == "accepted"
    assert responded is True
    assert after_expires == before_expires


@pytest.mark.asyncio
async def test_refresh_skips_urgency_escalated_booking(session, seed, uniq):
    """After urgency flip, refresh carve-out ends — offers follow instant path."""
    await _require_migration_014(session)
    pujari_id = await _pujari_id(session)
    bid, aid = uniq.id(), uniq.id()

    await _seed_booking_with_offer(
        session,
        booking_id=bid,
        assignment_id=aid,
        pujari_id=pujari_id,
        slot_date=uniq.date2,
        slot_time="16:00:00",
        booking_class="advance",
        expires_at_sql="now() + interval '30 minutes'",
        dispatch_deadline_sql="now() + interval '48 hours'",
        urgency_escalated=True,
    )
    await session.commit()

    conn = get_connection()
    try:
        before = _assignment_expires_at(conn, aid)
        refresh_advance_offers(conn)
        after = _assignment_expires_at(conn, aid)
    finally:
        conn.close()

    assert after == before
