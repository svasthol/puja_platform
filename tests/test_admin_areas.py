"""Sprint 4B — service areas admin + customer dropdown (A-AREAS, P-LAUNCH-AREA)."""
from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.api.v1.endpoints import admin_areas as areas_ep
from app.api.v1.endpoints import addresses as addr_ep
from app.api.v1.endpoints import service_areas as public_areas_ep
from app.core.dependencies import Principal
from app.schemas.address import AddressCreate, AddressUpdate
from app.schemas.service_area import ServiceAreaCreate, ServiceAreaUpdate


class _FakeRequest:
    client = None


def _admin(uid: uuid.UUID) -> Principal:
    return Principal(user_id=uid, app_context="admin", roles=("admin",))


def _customer(uid: uuid.UUID) -> Principal:
    return Principal(user_id=uid, app_context="customer", roles=())


async def _mk_admin(session) -> uuid.UUID:
    uid = uuid.uuid4()
    await session.execute(
        text("INSERT INTO users (id, full_name, phone) VALUES (:id, 'Admin', :ph)"),
        {"id": str(uid), "ph": "+91973" + uuid.uuid4().hex[:7]},
    )
    return uid


async def _ensure_area(session, *, city: str = "Hyderabad", zone: str) -> int:
    await session.execute(
        text(
            "INSERT INTO service_areas (city, zone_name, is_active) "
            "VALUES (:city, :zone, true) ON CONFLICT (city, zone_name) DO NOTHING"
        ),
        {"city": city, "zone": zone},
    )
    area_id = (
        await session.execute(
            text(
                "SELECT id FROM service_areas WHERE city = :city AND zone_name = :zone"
            ),
            {"city": city, "zone": zone},
        )
    ).scalar_one()
    return int(area_id)


@pytest.mark.asyncio
async def test_create_and_list_service_areas(session):
    actor = await _mk_admin(session)
    await session.commit()

    created = await areas_ep.create_service_area(
        ServiceAreaCreate(city="Hyderabad", zone_name="Kukatpally"),
        _FakeRequest(),
        _admin(actor),
        session,
    )
    assert created.zone_name == "Kukatpally"
    assert created.is_active is True

    listed = await areas_ep.list_service_areas(
        city=None, is_active=None, _p=_admin(actor), db=session
    )
    names = [a.zone_name for a in listed.areas]
    assert "Kukatpally" in names


@pytest.mark.asyncio
async def test_customer_lists_active_areas_only(session):
    customer_id = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
    active_id = await _ensure_area(session, zone="Active Zone")
    inactive_id = await _ensure_area(session, zone="Inactive Zone")
    await session.execute(
        text("UPDATE service_areas SET is_active = false WHERE id = :id"),
        {"id": inactive_id},
    )
    await session.commit()

    resp = await public_areas_ep.list_active_service_areas(
        city="Hyderabad", _p=_customer(customer_id), db=session
    )
    ids = {a.id for a in resp.areas}
    assert active_id in ids
    assert inactive_id not in ids


@pytest.mark.asyncio
async def test_address_create_requires_active_service_area(session, seed):
    customer_id = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
    area_id = await _ensure_area(session, zone="Addr Test Zone")
    await session.commit()

    out = await addr_ep.create_address(
        AddressCreate(
            line1="Line 1",
            city="Hyderabad",
            latitude=17.4,
            longitude=78.4,
            service_area_id=area_id,
        ),
        _customer(customer_id),
        session,
    )
    assert out.service_area_id == area_id


@pytest.mark.asyncio
async def test_address_rejects_inactive_service_area(session, seed):
    customer_id = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
    area_id = await _ensure_area(session, zone="Inactive Addr Zone")
    await session.execute(
        text("UPDATE service_areas SET is_active = false WHERE id = :id"),
        {"id": area_id},
    )
    await session.commit()

    with pytest.raises(HTTPException) as exc:
        await addr_ep.create_address(
            AddressCreate(
                line1="Line 1",
                city="Hyderabad",
                latitude=17.4,
                longitude=78.4,
                service_area_id=area_id,
            ),
            _customer(customer_id),
            session,
        )
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_deactivate_blocked_when_active_bookings(session, seed, uniq):
    actor = await _mk_admin(session)
    area_id = await _ensure_area(session, zone="Guard Zone")
    pujari_id = uuid.UUID("cccccccc-0000-0000-0000-000000000001")
    await session.execute(
        text(
            "INSERT INTO pujari_service_areas (pujari_id, service_area_id) "
            "VALUES (:pid, :aid) ON CONFLICT DO NOTHING"
        ),
        {"pid": str(pujari_id), "aid": area_id},
    )
    booking_id = uuid.uuid4()
    await session.execute(
        text(
            """
            INSERT INTO bookings (
                id, user_id, pujari_id, puja_id, address_id, status_id,
                cancellation_policy_id, scheduled_date, scheduled_time,
                duration_minutes, total_amount, payment_mode, amount_due_online,
                amount_due_offline, dispatch_mode
            )
            SELECT
                :bid,
                'aaaaaaaa-0000-0000-0000-000000000001',
                :pid,
                '11111111-1111-1111-1111-111111111111',
                'dddddddd-0000-0000-0000-000000000001',
                st.id,
                (SELECT id FROM cancellation_policies WHERE name='standard'),
                CAST(:slot_date AS date),
                '10:00',
                90,
                2100.00,
                'full_online',
                2100.00,
                0,
                'broadcast'
            FROM status_types st
            WHERE st.domain = 'booking' AND st.code = 'confirmed'
            """
        ),
        {"bid": str(booking_id), "pid": str(pujari_id), "slot_date": uniq.date},
    )
    await session.commit()

    with pytest.raises(HTTPException) as exc:
        await areas_ep.update_service_area(
            area_id,
            ServiceAreaUpdate(is_active=False),
            _FakeRequest(),
            _admin(actor),
            session,
        )
    assert exc.value.status_code == 409

    updated = await areas_ep.update_service_area(
        area_id,
        ServiceAreaUpdate(is_active=False, force_deactivate=True, change_reason="ops"),
        _FakeRequest(),
        _admin(actor),
        session,
    )
    assert updated.is_active is False


@pytest.mark.asyncio
async def test_address_update_service_area(session, seed):
    customer_id = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
    area_a = await _ensure_area(session, zone="Zone A")
    area_b = await _ensure_area(session, zone="Zone B")
    await session.commit()

    addr_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO addresses "
            "(id, user_id, line1, city, latitude, longitude, service_area_id, geom) "
            "VALUES (:id, :uid, 'L1', 'Hyd', 17.4, 78.4, :aid, "
            "ST_SetSRID(ST_MakePoint(78.4,17.4),4326)::geography)"
        ),
        {"id": str(addr_id), "uid": str(customer_id), "aid": area_a},
    )
    await session.commit()

    out = await addr_ep.update_address(
        addr_id,
        AddressUpdate(service_area_id=area_b),
        _customer(customer_id),
        session,
    )
    assert out.service_area_id == area_b
