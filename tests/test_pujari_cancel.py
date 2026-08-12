"""B-CANCEL — pujari cancel assigned confirmed booking (Phase 5)."""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.api.v1.endpoints import service_lifecycle as lifecycle_ep
from app.core.dependencies import Principal
from app.core.exceptions import StaleBookingState
from app.services.pujari_cancel_service import pujari_cancel_booking

CUSTOMER = "aaaaaaaa-0000-0000-0000-000000000001"
PUJARI_USER = "bbbbbbbb-0000-0000-0000-000000000001"
PUJARI_USER2 = "bbbbbbbb-0000-0000-0000-000000000002"
ADDRESS = "dddddddd-0000-0000-0000-000000000001"
PUJA = "11111111-1111-1111-1111-111111111111"


def _unique_slot_time(uniq) -> str:
    h = (int(uniq.id().replace("-", "")[:4], 16) % 12) + 8
    m = int(uniq.id().replace("-", "")[4:8], 16) % 60
    return f"{h:02d}:{m:02d}:00"


async def _pujari_ids(session) -> tuple[str, str]:
    p1 = (
        await session.execute(
            text("SELECT id FROM pujaris WHERE user_id = :uid"),
            {"uid": PUJARI_USER},
        )
    ).scalar_one()
    p2 = (
        await session.execute(
            text("SELECT id FROM pujaris WHERE user_id = :uid"),
            {"uid": PUJARI_USER2},
        )
    ).scalar_one()
    return str(p1), str(p2)


@pytest.fixture(autouse=True)
async def _clear_near_term_pujari_bookings(session, seed):
    p1, p2 = await _pujari_ids(session)
    await session.execute(
        text(
            """
            UPDATE bookings
            SET pujari_id = NULL, intended_pujari_id = NULL, updated_at = now()
            WHERE pujari_id = ANY(:pids)
              AND cancelled_at IS NULL
              AND scheduled_date <= CURRENT_DATE + INTERVAL '14 days'
            """
        ),
        {"pids": [p1, p2]},
    )
    await session.commit()


async def _insert_confirmed_with_accepted_assignment(
    session,
    uniq,
    *,
    pujari_id: str | None = None,
) -> tuple[str, str]:
    if pujari_id is None:
        pujari_id, _ = await _pujari_ids(session)
    bid = uniq.id()
    aid = uuid.uuid4()
    slot_time = _unique_slot_time(uniq)
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
                :d, CAST(:t AS time), 90, 2100, 2100, 0, 'full_online', now(),
                'broadcast', 'advance', now(), now()
            FROM status_types st
            WHERE st.domain = 'booking' AND st.code = 'confirmed'
            """
        ),
        {
            "bid": bid,
            "uid": CUSTOMER,
            "pid": pujari_id,
            "puja": PUJA,
            "addr": ADDRESS,
            "d": uniq.date,
            "t": slot_time,
        },
    )
    await session.execute(
        text(
            """
            INSERT INTO booking_dispatch_state (
                booking_id, round, radius_km, max_rounds,
                dispatch_starts_at, dispatch_deadline
            ) VALUES (
                :bid, 1, 3.0, 4, now() - interval '1 hour', now() + interval '1 day'
            )
            ON CONFLICT (booking_id) DO NOTHING
            """
        ),
        {"bid": bid},
    )
    await session.execute(
        text(
            """
            INSERT INTO booking_assignments (
                id, booking_id, pujari_id, status_id, offered_at, expires_at, responded_at
            ) VALUES (
                :aid, :bid, :pid,
                (SELECT id FROM status_types WHERE domain='assignment' AND code='accepted'),
                now(), now() + interval '5 minutes', now()
            )
            """
        ),
        {"aid": str(aid), "bid": bid, "pid": pujari_id},
    )
    await session.commit()
    return bid, str(aid)


@pytest.mark.asyncio
async def test_pujari_cancel_returns_to_requested(session, seed, uniq):
    pujari_id, _ = await _pujari_ids(session)
    bid, aid = await _insert_confirmed_with_accepted_assignment(session, uniq, pujari_id=pujari_id)

    with patch(
        "app.services.pujari_cancel_service.booking_events.publish_booking_event",
        return_value=0,
    ):
        async with session.begin():
            result = await pujari_cancel_booking(
                session,
                user_id=uuid.UUID(PUJARI_USER),
                booking_id=uuid.UUID(bid),
            )

    assert result["status"] == "requested"
    assert result["enqueue_rebroadcast"] == bid

    async with session.begin():
        row = (
            await session.execute(
                text(
                    """
                    SELECT st.code AS status, b.pujari_id, b.intended_pujari_id,
                           ast.code AS assignment_status
                    FROM bookings b
                    JOIN status_types st ON st.id = b.status_id
                    JOIN booking_assignments ba ON ba.id = :aid
                    JOIN status_types ast ON ast.id = ba.status_id
                    WHERE b.id = :bid
                    """
                ),
                {"bid": bid, "aid": aid},
            )
        ).mappings().first()

    assert row is not None
    assert row["status"] == "requested"
    assert row["pujari_id"] is None
    assert row["intended_pujari_id"] is None
    assert row["assignment_status"] == "revoked"


@pytest.mark.asyncio
async def test_pujari_cancel_wrong_pujari(session, seed, uniq):
    pujari_id, _ = await _pujari_ids(session)
    bid, _ = await _insert_confirmed_with_accepted_assignment(session, uniq, pujari_id=pujari_id)

    with pytest.raises(HTTPException) as exc:
        async with session.begin():
            await pujari_cancel_booking(
                session,
                user_id=uuid.UUID(PUJARI_USER2),
                booking_id=uuid.UUID(bid),
            )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_pujari_cancel_vs_start_race(session, seed, uniq):
    """LG-style: after start wins, pujari-cancel guard on confirmed sees 0 rows."""
    pujari_id, _ = await _pujari_ids(session)
    bid, _ = await _insert_confirmed_with_accepted_assignment(session, uniq, pujari_id=pujari_id)

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

    start = await session.execute(
        text(
            "UPDATE bookings SET status_id=:new, updated_at=now() "
            "WHERE id=:bid AND status_id=:expected"
        ),
        {"new": in_progress_id, "bid": bid, "expected": confirmed_id},
    )
    assert start.rowcount == 1
    await session.commit()

    with pytest.raises(HTTPException) as exc:
        await pujari_cancel_booking(
            session,
            user_id=uuid.UUID(PUJARI_USER),
            booking_id=uuid.UUID(bid),
        )
        await session.commit()
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_pujari_cancel_endpoint_enqueues_rebroadcast(session, seed, uniq):
    pujari_id, _ = await _pujari_ids(session)
    bid, _ = await _insert_confirmed_with_accepted_assignment(session, uniq, pujari_id=pujari_id)
    principal = Principal(user_id=uuid.UUID(PUJARI_USER), app_context="pujari", roles=())

    with (
        patch("app.workers.celery_app.celery_app.send_task") as mock_send,
        patch(
            "app.services.pujari_cancel_service.booking_events.publish_booking_event",
            return_value=0,
        ),
    ):
        resp = await lifecycle_ep.pujari_cancel(
            uuid.UUID(bid),
            p=principal,
            db=session,
        )
        await session.commit()

    assert resp.status == "requested"
    mock_send.assert_called_once_with(
        "app.workers.dispatch.rebroadcast_booking",
        args=[bid, True],
    )
