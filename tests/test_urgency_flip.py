"""DV2-URGENCY-FLIP — escalate beat + live urgency on GET /v1/offers (§21.6.E)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy import text

from app.api.v1.endpoints import offers as offers_ep
from app.core.dependencies import Principal
from app.workers.sweep import get_connection
from app.workers.urgency_flip import escalate_urgency_on_threshold

CUSTOMER = "aaaaaaaa-0000-0000-0000-000000000001"
PUJA = "11111111-1111-1111-1111-111111111111"
ADDRESS = "dddddddd-0000-0000-0000-000000000001"
PUJARI_USER1 = "bbbbbbbb-0000-0000-0000-000000000001"


def _pujari_principal() -> Principal:
    import uuid

    return Principal(
        user_id=uuid.UUID(PUJARI_USER1),
        app_context="pujari",
        roles=(),
    )


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


async def _seed_advance_offer_near_slot(
    session,
    *,
    booking_id: str,
    assignment_id: str,
    pujari_id: str,
    slot_offset_sql: str,
    expires_at_sql: str = "now() + interval '24 hours'",
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
                ({slot_offset_sql})::date,
                ({slot_offset_sql})::time,
                90, 2100, 2100, 0, 'full_online', now(),
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
                booking_id, dispatch_starts_at, dispatch_deadline, urgency_escalated_at
            ) VALUES (
                :bid, now() - interval '1 hour',
                ({slot_offset_sql}) - interval '3 hours',
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
                now(), {expires_at_sql}
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


def _urgency_escalated_at(conn, booking_id: str):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT urgency_escalated_at FROM booking_dispatch_state WHERE booking_id = %s",
            (booking_id,),
        )
        return cur.fetchone()[0]


def _offer_expires_at(conn, assignment_id: str):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT expires_at FROM booking_assignments WHERE id = %s",
            (assignment_id,),
        )
        return cur.fetchone()[0]


@pytest.mark.asyncio
async def test_escalate_flips_advance_booking_inside_lead_window(session, seed, uniq):
    """Slot within instant_lead_hours → urgency_escalated_at set, offer TTL shortened."""
    await _require_migration_014(session)
    pujari_id = await _pujari_id(session)
    bid, aid = uniq.id(), uniq.id()

    await _seed_advance_offer_near_slot(
        session,
        booking_id=bid,
        assignment_id=aid,
        pujari_id=pujari_id,
        slot_offset_sql="now() + interval '3 hours'",
        expires_at_sql="now() + interval '20 hours'",
    )
    await session.commit()

    conn = get_connection()
    try:
        before = _offer_expires_at(conn, aid)
        flipped = escalate_urgency_on_threshold(conn)
        after = _offer_expires_at(conn, aid)
        escalated_at = _urgency_escalated_at(conn, bid)
    finally:
        conn.close()

    assert bid in flipped
    assert escalated_at is not None
    assert after < before
    conn2 = get_connection()
    try:
        with conn2.cursor() as cur:
            cur.execute(
                "SELECT expires_at < now() + interval '5 minutes' FROM booking_assignments WHERE id = %s",
                (aid,),
            )
            short_ttl = cur.fetchone()[0]
    finally:
        conn2.close()
    assert short_ttl is True


@pytest.mark.asyncio
async def test_escalate_skips_advance_booking_outside_lead_window(session, seed, uniq):
    """Slot still > instant_lead_hours away → no flip."""
    await _require_migration_014(session)
    pujari_id = await _pujari_id(session)
    bid, aid = uniq.id(), uniq.id()

    await _seed_advance_offer_near_slot(
        session,
        booking_id=bid,
        assignment_id=aid,
        pujari_id=pujari_id,
        slot_offset_sql="now() + interval '10 hours'",
    )
    await session.commit()

    conn = get_connection()
    try:
        flipped = escalate_urgency_on_threshold(conn)
        escalated_at = _urgency_escalated_at(conn, bid)
    finally:
        conn.close()

    assert bid not in flipped
    assert escalated_at is None


@pytest.mark.asyncio
async def test_lg_urgency_flip_idempotent(session, seed, uniq, monkeypatch):
    """Two escalate ticks → marker set once; FCM enqueued once."""
    await _require_migration_014(session)
    pujari_id = await _pujari_id(session)
    bid, aid = uniq.id(), uniq.id()

    await _seed_advance_offer_near_slot(
        session,
        booking_id=bid,
        assignment_id=aid,
        pujari_id=pujari_id,
        slot_offset_sql="now() + interval '2 hours'",
    )
    await session.commit()

    sent: list[tuple] = []

    def _capture_send(task_name, args=None, **kwargs):
        sent.append((task_name, args))

    monkeypatch.setattr(
        "app.workers.urgency_flip.celery_app.send_task",
        _capture_send,
    )

    conn = get_connection()
    try:
        flipped1 = escalate_urgency_on_threshold(conn)
        for booking_id in flipped1:
            from app.workers.urgency_flip import celery_app

            celery_app.send_task(
                "app.workers.notifications.notify_offer_instant",
                args=[booking_id],
            )
        flipped2 = escalate_urgency_on_threshold(conn)
        for booking_id in flipped2:
            from app.workers.urgency_flip import celery_app

            celery_app.send_task(
                "app.workers.notifications.notify_offer_instant",
                args=[booking_id],
            )
    finally:
        conn.close()

    assert bid in flipped1
    assert flipped2 == []
    instant_calls = [
        c for c in sent if c[0] == "app.workers.notifications.notify_offer_instant"
    ]
    assert len(instant_calls) == 1
    assert instant_calls[0][1] == [bid]


@pytest.mark.asyncio
async def test_list_offers_live_urgency_inside_window(session, seed, uniq):
    """GET /offers computes urgency=instant from live lead_hours (§21.6.E)."""
    await _require_migration_014(session)
    pujari_id = await _pujari_id(session)
    bid, aid = uniq.id(), uniq.id()

    await _seed_advance_offer_near_slot(
        session,
        booking_id=bid,
        assignment_id=aid,
        pujari_id=pujari_id,
        slot_offset_sql="now() + interval '3 hours'",
    )
    await session.commit()

    result = await offers_ep.list_offers(limit=50, p=_pujari_principal(), db=session)
    offer = next(o for o in result.offers if str(o.booking_id) == bid)
    assert offer.booking_class == "advance"
    assert offer.urgency == "instant"
    assert offer.urgency_escalated is False


@pytest.mark.asyncio
async def test_list_offers_urgency_escalated_after_flip(session, seed, uniq):
    """After flip beat, urgency_escalated=true even if slot still advance-class."""
    await _require_migration_014(session)
    pujari_id = await _pujari_id(session)
    bid, aid = uniq.id(), uniq.id()

    await _seed_advance_offer_near_slot(
        session,
        booking_id=bid,
        assignment_id=aid,
        pujari_id=pujari_id,
        slot_offset_sql="now() + interval '10 hours'",
        urgency_escalated=True,
    )
    await session.commit()

    result = await offers_ep.list_offers(limit=50, p=_pujari_principal(), db=session)
    offer = next(o for o in result.offers if str(o.booking_id) == bid)
    assert offer.urgency == "advance"
    assert offer.urgency_escalated is True


@pytest.mark.asyncio
async def test_escalate_task_enqueues_offer_instant_fcm(session, seed, uniq, monkeypatch):
    """Beat task wires flip → notify_offer_instant."""
    await _require_migration_014(session)
    pujari_id = await _pujari_id(session)
    bid, aid = uniq.id(), uniq.id()

    await _seed_advance_offer_near_slot(
        session,
        booking_id=bid,
        assignment_id=aid,
        pujari_id=pujari_id,
        slot_offset_sql="now() + interval '2 hours'",
    )
    await session.commit()

    mock_redis = MagicMock()
    mock_redis.set.return_value = True
    monkeypatch.setattr("redis.from_url", lambda _url: mock_redis)

    sent: list[tuple] = []
    monkeypatch.setattr(
        "app.workers.urgency_flip.celery_app.send_task",
        lambda name, args=None, **kw: sent.append((name, args)),
    )

    from app.workers.urgency_flip import escalate_urgency_on_threshold_task

    result = escalate_urgency_on_threshold_task()
    assert result["flipped"] >= 1
    assert bid in result["booking_ids"]
    assert ("app.workers.notifications.notify_offer_instant", [bid]) in sent
