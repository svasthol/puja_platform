"""DV2-RM-ESCALATION — rm_escalation_scan beat (§21.6.F)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text

from app.workers.rm_escalation import scan_rm_escalations
from app.workers.sweep import get_connection

CUSTOMER = "aaaaaaaa-0000-0000-0000-000000000001"
PUJA = "11111111-1111-1111-1111-111111111111"
ADDRESS = "dddddddd-0000-0000-0000-000000000001"


async def _require_migration_014(session) -> None:
    row = (
        await session.execute(
            text(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'booking_dispatch_state'
                  AND column_name = 'rm_escalated_no_accept_at'
                """
            )
        )
    ).scalar_one_or_none()
    if row is None:
        pytest.skip("migration_014 not applied — run: python scripts/apply_migration_014.py")


async def _status_id(session, domain: str, code: str) -> int:
    return (
        await session.execute(
            text("SELECT id FROM status_types WHERE domain = :d AND code = :c"),
            {"d": domain, "c": code},
        )
    ).scalar_one()


async def _seed_unaccepted_advance(
    session,
    *,
    booking_id: str,
    slot_offset_sql: str,
    paid_at_sql: str = "now()",
    rm_no_accept_set: bool = False,
    rm_t24_set: bool = False,
) -> None:
    requested_id = await _status_id(session, "booking", "requested")
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
                ({slot_offset_sql})::date,
                ({slot_offset_sql})::time,
                90, 2100, 2100, 0, 'full_online', {paid_at_sql},
                'broadcast', 'advance', now(), now()
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
        },
    )
    await session.execute(
        text(
            f"""
            INSERT INTO booking_dispatch_state (
                booking_id, dispatch_starts_at, dispatch_deadline,
                rm_escalated_no_accept_at, rm_escalated_t24_at
            ) VALUES (
                :bid, now() - interval '1 hour',
                ({slot_offset_sql}) - interval '3 hours',
                {'now()' if rm_no_accept_set else 'NULL'},
                {'now()' if rm_t24_set else 'NULL'}
            )
            """
        ),
        {"bid": booking_id},
    )


def _markers(conn, booking_id: str) -> tuple:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT rm_escalated_no_accept_at, rm_escalated_t24_at
            FROM booking_dispatch_state WHERE booking_id = %s
            """,
            (booking_id,),
        )
        return cur.fetchone()


@pytest.mark.asyncio
async def test_rule1_no_accept_escalation(session, seed, uniq):
    """Paid 25h ago, slot >24h away → rm_escalated_no_accept_at set."""
    await _require_migration_014(session)
    bid = uniq.id()

    await _seed_unaccepted_advance(
        session,
        booking_id=bid,
        slot_offset_sql="now() + interval '48 hours'",
        paid_at_sql="now() - interval '25 hours'",
    )
    await session.commit()

    conn = get_connection()
    try:
        result = scan_rm_escalations(conn)
        no_accept_at, t24_at = _markers(conn, bid)
    finally:
        conn.close()

    assert bid in result["no_accept"]
    assert bid not in result["approaching"]
    assert no_accept_at is not None
    assert t24_at is None


@pytest.mark.asyncio
async def test_rule1_skips_recent_payment(session, seed, uniq):
    """Paid only 1h ago → no Rule 1 escalation."""
    await _require_migration_014(session)
    bid = uniq.id()

    await _seed_unaccepted_advance(
        session,
        booking_id=bid,
        slot_offset_sql="now() + interval '48 hours'",
        paid_at_sql="now() - interval '1 hour'",
    )
    await session.commit()

    conn = get_connection()
    try:
        result = scan_rm_escalations(conn)
        no_accept_at, _ = _markers(conn, bid)
    finally:
        conn.close()

    assert bid not in result["no_accept"]
    assert no_accept_at is None


@pytest.mark.asyncio
async def test_rule2_approaching_slot_escalation(session, seed, uniq):
    """Slot within 24h but >3h away → rm_escalated_t24_at set."""
    await _require_migration_014(session)
    bid = uniq.id()

    await _seed_unaccepted_advance(
        session,
        booking_id=bid,
        slot_offset_sql="now() + interval '10 hours'",
    )
    await session.commit()

    conn = get_connection()
    try:
        result = scan_rm_escalations(conn)
        no_accept_at, t24_at = _markers(conn, bid)
    finally:
        conn.close()

    assert bid in result["approaching"]
    assert bid not in result["no_accept"]
    assert t24_at is not None
    assert no_accept_at is None


@pytest.mark.asyncio
async def test_rule2_skips_inside_fail_window(session, seed, uniq):
    """Slot ≤3h away → automated backstop territory, no Rule 2 RM alert."""
    await _require_migration_014(session)
    bid = uniq.id()

    await _seed_unaccepted_advance(
        session,
        booking_id=bid,
        slot_offset_sql="now() + interval '2 hours'",
    )
    await session.commit()

    conn = get_connection()
    try:
        result = scan_rm_escalations(conn)
        _, t24_at = _markers(conn, bid)
    finally:
        conn.close()

    assert bid not in result["approaching"]
    assert t24_at is None


@pytest.mark.asyncio
async def test_rm_escalation_idempotent(session, seed, uniq):
    """Second scan tick → 0 rows, markers unchanged."""
    await _require_migration_014(session)
    bid = uniq.id()

    await _seed_unaccepted_advance(
        session,
        booking_id=bid,
        slot_offset_sql="now() + interval '10 hours'",
    )
    await session.commit()

    conn = get_connection()
    try:
        first = scan_rm_escalations(conn)
        before = _markers(conn, bid)
        second = scan_rm_escalations(conn)
        after = _markers(conn, bid)
    finally:
        conn.close()

    assert bid in first["approaching"]
    assert second["approaching"] == []
    assert second["no_accept"] == []
    assert before == after


@pytest.mark.asyncio
async def test_notify_rm_dispatch_escalation_sends_sms(session, seed, uniq):
    """Notification resolves RM and sends SMS + admin rows."""
    await _require_migration_014(session)
    bid = uniq.id()
    rm_phone = f"+9197{uniq.id().replace('-', '')[:8]}"

    await _seed_unaccepted_advance(
        session,
        booking_id=bid,
        slot_offset_sql="now() + interval '10 hours'",
    )
    await session.execute(
        text(
            """
            INSERT INTO relationship_managers (id, name, phone, is_active)
            VALUES (gen_random_uuid(), 'Dispatch RM', :ph, true)
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

    from app.workers.notifications import _notify_rm_dispatch_escalation_impl

    with patch(
        "app.workers.notifications.send_transactional_sms_sync",
        return_value=True,
    ) as mock_sms:
        result = _notify_rm_dispatch_escalation_impl(bid, "approaching")

    assert result["rm_sms"] is True
    mock_sms.assert_called_once()
    assert rm_phone in mock_sms.call_args[0][0]


@pytest.mark.asyncio
async def test_rm_escalation_task_enqueues_notifications(session, seed, uniq, monkeypatch):
    """Beat task wires scan → notify_rm_dispatch_escalation."""
    await _require_migration_014(session)
    bid = uniq.id()

    await _seed_unaccepted_advance(
        session,
        booking_id=bid,
        slot_offset_sql="now() + interval '10 hours'",
    )
    await session.commit()

    mock_redis = MagicMock()
    mock_redis.set.return_value = True
    monkeypatch.setattr("redis.from_url", lambda _url: mock_redis)

    sent: list[tuple] = []
    monkeypatch.setattr(
        "app.workers.rm_escalation.celery_app.send_task",
        lambda name, args=None, **kw: sent.append((name, args)),
    )

    from app.workers.rm_escalation import rm_escalation_scan_task

    result = rm_escalation_scan_task()
    assert bid in result["booking_ids"]["approaching"]
    assert (
        "app.workers.notifications.notify_rm_dispatch_escalation",
        [bid, "approaching"],
    ) in sent
