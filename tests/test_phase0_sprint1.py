"""Sprint 1 launch-gate tests — Phase 0 exit gate (spec/plans/STATUS.md)."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from app.core.exceptions import STALE_BOOKING_DETAIL, StaleBookingState
from app.workers.dispatch import rebroadcast_booking

CUSTOMER = "aaaaaaaa-0000-0000-0000-000000000001"
PUJARI = "cccccccc-0000-0000-0000-000000000001"
PUJA = "11111111-1111-1111-1111-111111111111"
ADDRESS = "dddddddd-0000-0000-0000-000000000001"


def test_stale_booking_state_exception_shape():
    exc = StaleBookingState()
    assert exc.status_code == 409
    assert exc.detail == STALE_BOOKING_DETAIL


async def _insert_requested_direct_booking(session, uniq, *, bid: str | None = None) -> str:
    booking_id = bid or uniq.id()
    await session.execute(
            text(
                """
                INSERT INTO bookings (
                    id, user_id, puja_id, address_id, status_id, cancellation_policy_id,
                    scheduled_date, scheduled_time, duration_minutes, total_amount,
                    amount_due_online, amount_due_offline, payment_mode, paid_at,
                    dispatch_mode, intended_pujari_id, created_at, updated_at
                ) VALUES (
                    :bid, :uid, :puja, :addr,
                    (SELECT id FROM status_types WHERE domain='booking' AND code='requested'),
                    (SELECT id FROM cancellation_policies WHERE name='standard'),
                    :d, '10:00', 90, 2100, 2100, 0, 'full_online', now(), 'direct',
                    :pj, now(), now()
                )
                """
            ),
            {
                "bid": booking_id,
                "uid": CUSTOMER,
                "puja": PUJA,
                "addr": ADDRESS,
                "d": uniq.date,
                "pj": PUJARI,
            },
        )
    await session.commit()
    return booking_id


async def _insert_confirmed_booking(session, uniq) -> str:
    bid = uniq.id()
    await session.execute(
            text(
                """
                INSERT INTO bookings (
                    id, user_id, puja_id, address_id, status_id, cancellation_policy_id,
                    scheduled_date, scheduled_time, duration_minutes, total_amount,
                    amount_due_online, amount_due_offline, payment_mode, paid_at,
                    dispatch_mode, pujari_id, intended_pujari_id, created_at, updated_at
                ) VALUES (
                    :bid, :uid, :puja, :addr,
                    (SELECT id FROM status_types WHERE domain='booking' AND code='confirmed'),
                    (SELECT id FROM cancellation_policies WHERE name='standard'),
                    :d, '10:00', 90, 2100, 2100, 0, 'full_online', now(), 'broadcast',
                    :pj, :pj, now(), now()
                )
                """
            ),
            {"bid": bid, "uid": CUSTOMER, "puja": PUJA, "addr": ADDRESS, "d": uniq.date, "pj": PUJARI},
        )
    await session.commit()
    return bid


@pytest.mark.asyncio
async def test_dispatch_choice_guard_second_update_gets_zero_rows(session, seed, uniq):
    """LG-dispatch-choice-race: second broadcast conversion sees 0 rows (→ StaleBookingState in app)."""
    bid = await _insert_requested_direct_booking(session, uniq)
    requested_id = (
        await session.execute(
            text("SELECT id FROM status_types WHERE domain='booking' AND code='requested'")
        )
    ).scalar_one()
    guard_sql = text(
        """
        UPDATE bookings
        SET intended_pujari_id = NULL, dispatch_mode = 'broadcast', updated_at = now()
        WHERE id = :bid AND status_id = :sid AND dispatch_mode = 'direct' AND pujari_id IS NULL
        """
    )
    first = await session.execute(guard_sql, {"bid": bid, "sid": requested_id})
    assert first.rowcount == 1
    await session.commit()

    second = await session.execute(guard_sql, {"bid": bid, "sid": requested_id})
    assert second.rowcount == 0
    await session.commit()


@pytest.mark.asyncio
async def test_start_then_cancel_guard_fails(session, seed, uniq):
    """LG-cancel-vs-start: after start wins, cancel guard on confirmed sees 0 rows."""
    bid = await _insert_confirmed_booking(session, uniq)
    confirmed_id = (
        await session.execute(
            text("SELECT id FROM status_types WHERE domain='booking' AND code='confirmed'")
        )
    ).scalar_one()
    in_progress_id = (
        await session.execute(
            text("SELECT id FROM status_types WHERE domain='booking' AND code='in_progress'")
        )
    ).scalar_one()
    cancelled_id = (
        await session.execute(
            text("SELECT id FROM status_types WHERE domain='booking' AND code='cancelled'")
        )
    ).scalar_one()

    start = await session.execute(
        text(
            "UPDATE bookings SET status_id=:new, updated_at=now() "
            "WHERE id=:bid AND status_id=:expected"
        ),
        {"new": in_progress_id, "bid": bid, "expected": confirmed_id},
    )
    assert start.rowcount == 1
    await session.commit()

    cancel = await session.execute(
        text(
            "UPDATE bookings SET cancelled_at=now(), status_id=:new, updated_at=now() "
            "WHERE id=:bid AND status_id=:expected AND cancelled_at IS NULL"
        ),
        {"new": cancelled_id, "bid": bid, "expected": confirmed_id},
    )
    assert cancel.rowcount == 0
    await session.commit()


@pytest.mark.asyncio
async def test_fresh_rebroadcast_resets_round_to_one(session, seed, uniq):
    """LG-fresh-dispatch: fresh=True resets round 3 → dispatch starts at round 1 / 3 km."""
    bid = uniq.id()
    await session.execute(
        text(
            """
            INSERT INTO bookings (
                id, user_id, puja_id, address_id, status_id, cancellation_policy_id,
                scheduled_date, scheduled_time, duration_minutes, total_amount,
                amount_due_online, amount_due_offline, payment_mode, paid_at,
                dispatch_mode, created_at, updated_at
            ) VALUES (
                :bid, :uid, :puja, :addr,
                (SELECT id FROM status_types WHERE domain='booking' AND code='requested'),
                (SELECT id FROM cancellation_policies WHERE name='standard'),
                :d, '10:00', 90, 2100, 2100, 0, 'full_online', now(), 'broadcast',
                now(), now()
            )
            """
        ),
        {"bid": bid, "uid": CUSTOMER, "puja": PUJA, "addr": ADDRESS, "d": uniq.date},
    )
    await session.execute(
        text(
            "INSERT INTO booking_dispatch_state (booking_id, round, radius_km, max_rounds) "
            "VALUES (:bid, 3, 10.0, 4)"
        ),
        {"bid": bid},
    )
    await session.commit()

    result = rebroadcast_booking(bid, fresh=True)
    assert result.get("skipped") != "round_cas"
    assert result.get("round") == 1

    row = (
        await session.execute(
            text("SELECT round, radius_km FROM booking_dispatch_state WHERE booking_id=:bid"),
            {"bid": bid},
        )
    ).first()
    assert row is not None
    assert row[0] == 1
    assert float(row[1]) == 3.0
