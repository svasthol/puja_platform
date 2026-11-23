"""Offer-round policy: zero-offer passes are free; admin `max_offer_rounds` caps offer rounds."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from app.workers.dispatch import rebroadcast_booking
from app.workers.sweep import bookings_needing_rebroadcast, get_connection

from tests.test_inbox_cap import (
    _clear_presence,
    _clear_pujari_live_offers,
    _ensure_pujari_dispatch_ready,
    _insert_broadcast_target,
    _require_migration_014,
    _reset_dispatch_presence_state,
    _set_presence,
    _unique_slot_time,
)


async def _set_max_offer_rounds(session, value: int | None) -> None:
    if value is None:
        await session.execute(text("DELETE FROM platform_settings WHERE key = 'max_offer_rounds'"))
    else:
        await session.execute(
            text(
                """
                INSERT INTO platform_settings (key, value_json, updated_at)
                VALUES ('max_offer_rounds', CAST(:v AS jsonb), now())
                ON CONFLICT (key) DO UPDATE SET value_json = CAST(:v AS jsonb), updated_at = now()
                """
            ),
            {"v": str(value)},
        )
    await session.commit()


async def _insert_dispatch_state(session, bid: str, *, round_: int) -> None:
    await session.execute(
        text(
            """
            INSERT INTO booking_dispatch_state (
                booking_id, round, max_rounds, last_dispatched,
                dispatch_starts_at, dispatch_deadline
            ) VALUES (
                :bid, :r, 4, now(), now() - interval '1 minute', now() + interval '2 hours'
            )
            """
        ),
        {"bid": bid, "r": round_},
    )


async def _round_and_status(session, bid: str) -> tuple[int, bool, str]:
    row = (
        await session.execute(
            text(
                """
                SELECT bds.round, bds.last_dispatched IS NOT NULL, st.code
                FROM bookings b
                JOIN status_types st ON st.id = b.status_id
                JOIN booking_dispatch_state bds ON bds.booking_id = b.id
                WHERE b.id = :bid
                """
            ),
            {"bid": bid},
        )
    ).one()
    return int(row[0]), bool(row[1]), str(row[2])


async def _new_target(session, uniq) -> str:
    bid = uniq.id()
    await _insert_broadcast_target(
        session,
        booking_id=bid,
        slot_date=uniq.date,
        slot_time=_unique_slot_time(uniq),
        booking_class="advance",
    )
    return bid


@pytest.mark.asyncio
async def test_zero_offer_passes_do_not_consume_rounds(session, seed, uniq):
    await _require_migration_014(session)
    p1, p2 = await _ensure_pujari_dispatch_ready(session)
    await _set_max_offer_rounds(session, None)
    await _reset_dispatch_presence_state(session)
    bid = await _new_target(session, uniq)
    await session.commit()

    _clear_presence(p1, p2)
    for _ in range(3):
        result = rebroadcast_booking(bid)
        assert result.get("offers") == 0
        assert result.get("round") == 0

    session.expire_all()
    round_, dispatched, status = await _round_and_status(session, bid)
    assert (round_, dispatched, status) == (0, True, "requested")

    conn = get_connection()
    try:
        assert bid in bookings_needing_rebroadcast(conn)
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_round_past_legacy_max_rounds_still_rebroadcasts(session, seed, uniq):
    """Legacy `max_rounds` column (4) must not strand an in-window booking when cap is off."""
    await _require_migration_014(session)
    p1, p2 = await _ensure_pujari_dispatch_ready(session)
    await _clear_pujari_live_offers(session, p1, p2)
    await _set_max_offer_rounds(session, None)
    await _reset_dispatch_presence_state(session)
    bid = await _new_target(session, uniq)
    await _insert_dispatch_state(session, bid, round_=4)
    await session.commit()

    conn = get_connection()
    try:
        assert bid in bookings_needing_rebroadcast(conn)
    finally:
        conn.close()

    _set_presence(p1, p2)
    try:
        result = rebroadcast_booking(bid)
    finally:
        _clear_presence(p1, p2)
    assert result.get("offers", 0) >= 1
    assert result.get("round") == 5


@pytest.mark.asyncio
async def test_offer_round_cap_exhausts_when_no_live_offer(session, seed, uniq):
    await _require_migration_014(session)
    await _ensure_pujari_dispatch_ready(session)
    bid = await _new_target(session, uniq)
    await _insert_dispatch_state(session, bid, round_=2)
    await session.commit()

    await _set_max_offer_rounds(session, 2)
    try:
        conn = get_connection()
        try:
            assert bid in bookings_needing_rebroadcast(conn)
        finally:
            conn.close()
        result = rebroadcast_booking(bid)
    finally:
        await _set_max_offer_rounds(session, None)

    assert result.get("status") == "failed_no_pujari"
    session.expire_all()
    _, _, status = await _round_and_status(session, bid)
    assert status == "failed_no_pujari"


@pytest.mark.asyncio
async def test_offer_round_cap_keeps_booking_with_live_offer(session, seed, uniq):
    await _require_migration_014(session)
    p1, _ = await _ensure_pujari_dispatch_ready(session)
    bid = await _new_target(session, uniq)
    await _insert_dispatch_state(session, bid, round_=2)
    await session.execute(
        text(
            """
            INSERT INTO booking_assignments (id, booking_id, pujari_id, status_id, offered_at, expires_at)
            VALUES (
                gen_random_uuid(), :bid, :pid,
                (SELECT id FROM status_types WHERE domain='assignment' AND code='offered'),
                now(), now() + interval '24 hours'
            )
            """
        ),
        {"bid": bid, "pid": p1},
    )
    await session.commit()

    await _set_max_offer_rounds(session, 2)
    try:
        result = rebroadcast_booking(bid)
    finally:
        await _set_max_offer_rounds(session, None)

    assert result.get("skipped") == "live_offer_pending"
    session.expire_all()
    round_, _, status = await _round_and_status(session, bid)
    assert (round_, status) == (2, "requested")
