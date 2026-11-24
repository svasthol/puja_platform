"""Launch service boundary polygon (§21.13)."""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.core.config import get_settings
from app.services.service_boundary import (
    OUT_OF_SERVICE_AREA,
    assert_serviceable,
    init_boundary,
    is_serviceable,
    load_boundary_from_path,
    resolve_geojson_path,
)
from app.services.service_boundary_settings import load_service_boundary_enabled

_ROOT = Path(__file__).resolve().parents[1]
_QA = _ROOT / "spec/geo/hyderabad_launch_service_qa.json"


@pytest.fixture(autouse=True)
async def _service_boundary_toggle_off(session):
    """Local DB may retain toggle from prior runs; tests assume default false."""
    await session.execute(
        text(
            "UPDATE platform_settings SET value_json = 'false'::jsonb "
            "WHERE key = 'service_boundary_enabled'"
        )
    )
    await session.commit()


def test_qa_json_vectors():
    cases = json.loads(_QA.read_text(encoding="utf-8"))
    for name, case in cases.items():
        got = is_serviceable(case["lat"], case["lng"])
        assert got == case["expect"], name


def test_load_swapped_lng_lat_order():
    settings = get_settings()
    path = resolve_geojson_path(settings.SERVICE_BOUNDARY_GEOJSON_PATH)
    snap = load_boundary_from_path(path)
    assert snap.vertex_count >= 4


def test_assert_raises_out_of_area():
    with pytest.raises(HTTPException) as exc:
        assert_serviceable(19.076, 72.8777, route="test")
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == OUT_OF_SERVICE_AREA


@pytest.mark.asyncio
async def test_boundary_disabled_by_default(session, seed):
    enabled = await load_service_boundary_enabled(session)
    assert enabled is False


@pytest.mark.asyncio
async def test_address_rejects_outside_when_enabled(session, seed):
    from app.api.v1.endpoints import addresses as addr_ep
    from app.core.dependencies import Principal
    from app.schemas.address import AddressCreate
    customer_id = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
    await session.execute(
        text(
            """
            INSERT INTO platform_settings (key, value_json, updated_at)
            VALUES ('service_boundary_enabled', 'true'::jsonb, now())
            ON CONFLICT (key) DO UPDATE SET value_json = 'true'::jsonb, updated_at = now()
            """
        )
    )
    area_id = (
        await session.execute(
            text(
                "SELECT id FROM service_areas WHERE city='Hyderabad' AND zone_name='Test Zone'"
            )
        )
    ).scalar_one()

    with pytest.raises(HTTPException) as exc:
        await addr_ep.create_address(
            AddressCreate(
                line1="Mumbai",
                city="Mumbai",
                latitude=19.076,
                longitude=72.8777,
                service_area_id=area_id,
            ),
            Principal(user_id=customer_id, app_context="customer", roles=()),
            session,
        )
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == OUT_OF_SERVICE_AREA

    await session.execute(
        text(
            "UPDATE platform_settings SET value_json = 'false'::jsonb "
            "WHERE key = 'service_boundary_enabled'"
        )
    )


@pytest.mark.asyncio
async def test_public_probe_skips_geometry_when_toggle_off(session, seed):
    from app.api.v1.endpoints import serviceability as svc_ep

    resp = await svc_ep.probe_serviceability(19.076, 72.8777, session)
    assert resp.serviceable is True
    assert resp.code is None


@pytest.mark.asyncio
async def test_checkout_rejects_outside_address_when_enabled(session, seed, uniq, monkeypatch):
    """prepare_booking_checkout must enforce polygon when toggle is on."""
    import datetime as dt
    from decimal import Decimal

    from app.schemas.booking import BookingCreate
    from app.services import booking_service

    user_id = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
    puja_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    outside_id = uuid.uuid4()
    now = dt.datetime(2036, 6, 15, 10, 0, tzinfo=dt.UTC)
    slot_date = dt.date.fromisoformat(uniq.date2)
    slot_time = dt.time(10, 0)

    await session.execute(
        text(
            """
            INSERT INTO platform_settings (key, value_json, updated_at)
            VALUES ('service_boundary_enabled', 'true'::jsonb, now())
            ON CONFLICT (key) DO UPDATE SET value_json = 'true'::jsonb, updated_at = now()
            """
        )
    )
    area_id = (
        await session.execute(
            text(
                "SELECT id FROM service_areas WHERE city='Hyderabad' AND zone_name='Test Zone'"
            )
        )
    ).scalar_one()
    await session.execute(
        text(
            """
            INSERT INTO addresses (
                id, user_id, line1, city, latitude, longitude,
                service_area_id, geom
            ) VALUES (
                :aid, :uid, 'Outside', 'Mumbai', 19.076, 72.8777,
                :area,
                ST_SetSRID(ST_MakePoint(72.8777, 19.076), 4326)::geography
            )
            """
        ),
        {"aid": str(outside_id), "uid": str(user_id), "area": area_id},
    )
    hold_id = uuid.uuid4()
    await session.execute(
        text(
            """
            INSERT INTO slot_holds (
                id, user_id, pujari_id, slot_date, slot_time, held_at, expires_at
            ) VALUES (
                :hid, :uid, NULL, :sd, :st, :now, :now + interval '5 min'
            )
            """
        ),
        {
            "hid": str(hold_id),
            "uid": str(user_id),
            "sd": slot_date,
            "st": slot_time,
            "now": now,
        },
    )
    await session.execute(
        text(
            """
            INSERT INTO platform_settings (key, value_json) VALUES
            ('advance_booking_amount', '{"amount": 250.00, "currency": "INR"}')
            ON CONFLICT (key) DO NOTHING
            """
        )
    )
    await session.commit()

    class _FixedDatetime(dt.datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001
            return now if tz is None else now.astimezone(tz)

    monkeypatch.setattr(booking_service.dt, "datetime", _FixedDatetime)

    payload = BookingCreate(
        hold_id=hold_id,
        puja_id=puja_id,
        address_id=outside_id,
        payment_mode="full_online",
    )
    with pytest.raises(HTTPException) as exc:
        await booking_service.prepare_booking_checkout(
            session, user_id=user_id, payload=payload
        )
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == OUT_OF_SERVICE_AREA

    await session.execute(
        text(
            "UPDATE platform_settings SET value_json = 'false'::jsonb "
            "WHERE key = 'service_boundary_enabled'"
        )
    )