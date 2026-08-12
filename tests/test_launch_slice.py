"""Launch slice — NO-DIRECT, OFFERS area label, pujari bookings list."""
from __future__ import annotations

import datetime as dt
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.api.v1.endpoints import bookings as bookings_ep
from app.api.v1.endpoints import offers as offers_ep
from app.api.v1.endpoints import pujari_bookings as pujari_bookings_ep
from app.core.dependencies import Principal
from app.schemas.booking import DispatchChoice, SlotHoldRequest
from app.services.cancellation_service import cancel_booking
from app.services.relationship_manager import assign_rm_on_confirm

CUSTOMER = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
PUJARI_USER = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000001")
PUJARI = uuid.UUID("cccccccc-0000-0000-0000-000000000001")
ADDRESS = "dddddddd-0000-0000-0000-000000000001"
PUJA = uuid.UUID("11111111-1111-1111-1111-111111111111")


def _customer() -> Principal:
    return Principal(user_id=CUSTOMER, app_context="customer", roles=())


def _pujari() -> Principal:
    return Principal(user_id=PUJARI_USER, app_context="pujari", roles=())


def _unique_slot_time(uniq) -> str:
    h = (int(uniq.id().replace("-", "")[:4], 16) % 12) + 8
    m = int(uniq.id().replace("-", "")[4:8], 16) % 60
    return f"{h:02d}:{m:02d}:00"


async def _make_live_offer(session, uniq) -> tuple[str, str]:
    bid, aid = uniq.id(), uniq.id()
    slot_time = _unique_slot_time(uniq)
    pujari_id = (
        await session.execute(
            text("SELECT id::text FROM pujaris WHERE user_id = :u"),
            {"u": str(PUJARI_USER)},
        )
    ).scalar_one()
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
                CAST(:d AS date), CAST(:t AS time), 90, 2100, 2100, 0, 'full_online', now(),
                'broadcast', 'instant', now(), now()
            )
            """
        ),
        {
            "bid": bid,
            "uid": str(CUSTOMER),
            "puja": str(PUJA),
            "addr": ADDRESS,
            "d": uniq.date,
            "t": slot_time,
        },
    )
    await session.execute(
        text(
            """
            INSERT INTO booking_assignments (
                id, booking_id, pujari_id, status_id, offered_at, expires_at
            ) VALUES (
                :aid, :bid, :pid,
                (SELECT id FROM status_types WHERE domain='assignment' AND code='offered'),
                now(), now() + interval '2 min'
            )
            """
        ),
        {"aid": aid, "bid": bid, "pid": pujari_id},
    )
    await session.commit()
    return bid, aid


async def _find_pujari_booking_summary(session, bid: str):
    """Paginate list — dev DB may have many historical rows for seed pujari."""
    cursor = None
    while True:
        page = await pujari_bookings_ep.list_pujari_bookings(
            cursor=cursor, limit=50, p=_pujari(), db=session
        )
        for row in page.bookings:
            if str(row.id) == bid:
                return row
        if not page.next_cursor:
            return None
        cursor = page.next_cursor


async def _confirm_booking(session, aid: str, bid: str) -> None:
    await session.execute(
        text(
            """
            UPDATE booking_assignments
            SET status_id = (
                SELECT id FROM status_types WHERE domain='assignment' AND code='accepted'
            ),
            responded_at = now()
            WHERE id = :aid
            """
        ),
        {"aid": aid},
    )
    await assign_rm_on_confirm(session, uuid.UUID(bid))
    await session.commit()


@pytest.mark.asyncio
async def test_slot_hold_rejects_pujari_id(session, seed, uniq):
    with pytest.raises(HTTPException) as exc:
        await bookings_ep.create_slot_hold(
            SlotHoldRequest(
                pujari_id=PUJARI,
                date=dt.date.fromisoformat(uniq.date),
                time=dt.time(10, 0),
            ),
            _customer(),
            session,
        )
    assert exc.value.status_code == 410


@pytest.mark.asyncio
async def test_checkout_quote_rejects_pujari_id(session, seed, uniq):
    with pytest.raises(HTTPException) as exc:
        await bookings_ep.checkout_quote(
            puja_id=PUJA,
            pujari_id=PUJARI,
            addon_ids=[],
            _p=_customer(),
            db=session,
        )
    assert exc.value.status_code == 410


@pytest.mark.asyncio
async def test_dispatch_choice_disabled_at_launch(session, seed, uniq):
    with pytest.raises(HTTPException) as exc:
        await bookings_ep.dispatch_choice(
            uuid.UUID(uniq.id()),
            DispatchChoice(action="broadcast"),
            _customer(),
            session,
        )
    assert exc.value.status_code == 410


@pytest.mark.asyncio
async def test_list_offers_includes_area_label_and_puja(session, seed, uniq):
    _bid, _aid = await _make_live_offer(session, uniq)
    result = await offers_ep.list_offers(limit=50, p=_pujari(), db=session)
    assert len(result.offers) >= 1
    offer = next(o for o in result.offers if str(o.booking_id) == _bid)
    assert offer.puja_name == "Test Puja"
    expected_label = (
        await session.execute(
            text(
                "SELECT sa.zone_name FROM addresses a "
                "JOIN service_areas sa ON sa.id = a.service_area_id "
                "WHERE a.id = :aid"
            ),
            {"aid": ADDRESS},
        )
    ).scalar_one()
    assert offer.area_label == expected_label
    assert offer.scheduled_date is not None
    assert offer.total_amount == 2100


@pytest.mark.asyncio
async def test_list_offers_excludes_address_fields(session, seed, uniq):
    await _make_live_offer(session, uniq)
    result = await offers_ep.list_offers(limit=50, p=_pujari(), db=session)
    offer = result.offers[0]
    dumped = offer.model_dump()
    assert "line1" not in dumped
    assert "latitude" not in dumped
    assert "phone" not in dumped


@pytest.mark.asyncio
async def test_list_offers_excludes_customer_cancelled_booking(session, seed, uniq):
    bid, aid = await _make_live_offer(session, uniq)
    before = await offers_ep.list_offers(limit=50, p=_pujari(), db=session)
    assert any(str(o.assignment_id) == aid for o in before.offers)

    await cancel_booking(session, user_id=CUSTOMER, booking_id=uuid.UUID(bid))
    await session.commit()

    after = await offers_ep.list_offers(limit=50, p=_pujari(), db=session)
    assert not any(str(o.assignment_id) == aid for o in after.offers)

    row = (
        await session.execute(
            text(
                """
                SELECT st.code AS status, ba.responded_at IS NOT NULL AS resolved
                FROM booking_assignments ba
                JOIN status_types st ON st.id = ba.status_id
                WHERE ba.id = :aid
                """
            ),
            {"aid": aid},
        )
    ).mappings().one()
    assert row["status"] == "expired"
    assert row["resolved"]


@pytest.mark.asyncio
async def test_pujari_bookings_list_after_confirm(session, seed, uniq):
    bid, aid = await _make_live_offer(session, uniq)
    await _confirm_booking(session, aid, bid)

    row = await _find_pujari_booking_summary(session, bid)
    assert row is not None, "confirmed booking missing from pujari list"
    assert row.status == "confirmed"
    assert row.puja_name == "Test Puja"
    assert row.area_label is not None


@pytest.mark.asyncio
async def test_pujari_bookings_list_excludes_unassigned(session, seed, uniq):
    bid, _aid = await _make_live_offer(session, uniq)
    page = await pujari_bookings_ep.list_pujari_bookings(
        cursor=None, limit=50, p=_pujari(), db=session
    )
    assert bid not in {str(b.id) for b in page.bookings}
