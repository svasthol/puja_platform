"""Sprint 4B — relationship managers (A-RM, P-LAUNCH-RM)."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.api.v1.endpoints import admin_rm as rm_ep
from app.api.v1.endpoints import bookings as bookings_ep
from app.api.v1.endpoints import pujari_bookings as pujari_bookings_ep
from app.core.dependencies import Principal
from app.schemas.relationship_manager import (
    RelationshipManagerCreate,
    RelationshipManagerUpdate,
)
from app.services.relationship_manager import assign_rm_on_confirm

CUSTOMER = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
PUJARI_USER = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000001")
PUJARI = uuid.UUID("cccccccc-0000-0000-0000-000000000001")
ADDRESS = "dddddddd-0000-0000-0000-000000000001"
PUJA = "11111111-1111-1111-1111-111111111111"


class _FakeRequest:
    client = None


def _admin(uid: uuid.UUID) -> Principal:
    return Principal(user_id=uid, app_context="admin", roles=("admin",))


def _customer() -> Principal:
    return Principal(user_id=CUSTOMER, app_context="customer", roles=())


def _pujari() -> Principal:
    return Principal(user_id=PUJARI_USER, app_context="pujari", roles=())


async def _mk_admin(session) -> uuid.UUID:
    uid = uuid.uuid4()
    await session.execute(
        text("INSERT INTO users (id, full_name, phone) VALUES (:id, 'Admin', :ph)"),
        {"id": str(uid), "ph": "+91974" + uuid.uuid4().hex[:7]},
    )
    return uid


async def _make_requested_booking_with_offer(
    session, uniq, *, slot_date: str | None = None, slot_time: str = "10:00"
) -> tuple[str, str]:
    bid, aid = uniq.id(), uniq.id()
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
                CAST(:d AS date), CAST(:t AS time), 90, 2100, 2100, 0, 'full_online', now(),
                'broadcast', now(), now()
            )
            """
        ),
        {
            "bid": bid,
            "uid": str(CUSTOMER),
            "puja": PUJA,
            "addr": ADDRESS,
            "d": slot_date or uniq.date,
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
        {"aid": aid, "bid": bid, "pid": str(PUJARI)},
    )
    await session.commit()
    return bid, aid


async def _accept_assignment_and_assign_rm(session, aid: str, bid: str) -> None:
    """Trigger-3 accept path without Redis publish (test isolation)."""
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
async def test_create_rm_and_set_default(session):
    actor = await _mk_admin(session)
    await session.commit()

    created = await rm_ep.create_relationship_manager(
        RelationshipManagerCreate(
            name="Ops RM",
            phone="+919876543210",
            city="Hyderabad",
            set_as_default=True,
        ),
        _FakeRequest(),
        _admin(actor),
        session,
    )
    assert created.is_default is True

    default = await rm_ep.get_default_relationship_manager(
        _p=_admin(actor), db=session
    )
    assert default.relationship_manager_id == created.id
    assert default.name == "Ops RM"


@pytest.mark.asyncio
async def test_assign_rm_on_accept(session, seed, uniq):
    actor = await _mk_admin(session)
    await rm_ep.create_relationship_manager(
        RelationshipManagerCreate(
            name="Launch RM",
            phone="+919800000001",
            city="Hyderabad",
            set_as_default=True,
        ),
        _FakeRequest(),
        _admin(actor),
        session,
    )
    await session.commit()

    bid, aid = await _make_requested_booking_with_offer(session, uniq, slot_time="10:15")
    await _accept_assignment_and_assign_rm(session, aid, bid)

    rm_id = (
        await session.execute(
            text("SELECT relationship_manager_id FROM bookings WHERE id = :bid"),
            {"bid": bid},
        )
    ).scalar_one()
    assert rm_id is not None


@pytest.mark.asyncio
async def test_customer_sees_rm_after_confirm(session, seed, uniq):
    actor = await _mk_admin(session)
    rm = await rm_ep.create_relationship_manager(
        RelationshipManagerCreate(
            name="Customer RM",
            phone="+919800000002",
            set_as_default=True,
        ),
        _FakeRequest(),
        _admin(actor),
        session,
    )
    await session.commit()

    bid, aid = await _make_requested_booking_with_offer(session, uniq, slot_time="10:30")
    await _accept_assignment_and_assign_rm(session, aid, bid)

    detail = await bookings_ep.get_booking(uuid.UUID(bid), _customer(), session)
    assert detail["relationship_manager"] is not None
    assert detail["relationship_manager"]["name"] == "Customer RM"
    assert detail["relationship_manager"]["phone"] == "+919800000002"
    assert detail["relationship_manager"]["id"] == rm.id


@pytest.mark.asyncio
async def test_customer_no_rm_before_confirm(session, seed, uniq):
    bid, _aid = await _make_requested_booking_with_offer(
        session, uniq, slot_date=uniq.date2, slot_time="11:00"
    )
    detail = await bookings_ep.get_booking(uuid.UUID(bid), _customer(), session)
    assert detail["relationship_manager"] is None


@pytest.mark.asyncio
async def test_pujari_booking_detail_includes_rm_and_address(session, seed, uniq):
    actor = await _mk_admin(session)
    await rm_ep.create_relationship_manager(
        RelationshipManagerCreate(
            name="Pujari RM",
            phone="+919800000003",
            set_as_default=True,
        ),
        _FakeRequest(),
        _admin(actor),
        session,
    )
    await session.commit()

    bid, aid = await _make_requested_booking_with_offer(
        session, uniq, slot_date=uniq.date2, slot_time="10:45"
    )
    await _accept_assignment_and_assign_rm(session, aid, bid)

    detail = await pujari_bookings_ep.get_pujari_booking(
        uuid.UUID(bid), _pujari(), session
    )
    assert detail.relationship_manager is not None
    assert detail.relationship_manager.name == "Pujari RM"
    assert detail.address.line1 == "L1"
    assert detail.map_url is not None


@pytest.mark.asyncio
async def test_deactivate_clears_default(session):
    actor = await _mk_admin(session)
    rm = await rm_ep.create_relationship_manager(
        RelationshipManagerCreate(
            name="Temp RM",
            phone="+919800000004",
            set_as_default=True,
        ),
        _FakeRequest(),
        _admin(actor),
        session,
    )
    await session.commit()

    await rm_ep.update_relationship_manager(
        rm.id,
        RelationshipManagerUpdate(is_active=False, change_reason="offboard"),
        _FakeRequest(),
        _admin(actor),
        session,
    )
    await session.commit()

    default = await rm_ep.get_default_relationship_manager(
        _p=_admin(actor), db=session
    )
    assert default.relationship_manager_id is None


@pytest.mark.asyncio
async def test_assign_rm_on_confirm_idempotent(session, seed, uniq):
    actor = await _mk_admin(session)
    await rm_ep.create_relationship_manager(
        RelationshipManagerCreate(
            name="Idempotent RM",
            phone="+919800000005",
            set_as_default=True,
        ),
        _FakeRequest(),
        _admin(actor),
        session,
    )
    await session.commit()

    bid, aid = await _make_requested_booking_with_offer(
        session, uniq, slot_date=uniq.date2, slot_time="12:15"
    )
    await _accept_assignment_and_assign_rm(session, aid, bid)

    first = (
        await session.execute(
            text("SELECT relationship_manager_id FROM bookings WHERE id = :bid"),
            {"bid": bid},
        )
    ).scalar_one()

    await assign_rm_on_confirm(session, uuid.UUID(bid))
    await session.commit()

    second = (
        await session.execute(
            text("SELECT relationship_manager_id FROM bookings WHERE id = :bid"),
            {"bid": bid},
        )
    ).scalar_one()
    assert first == second
