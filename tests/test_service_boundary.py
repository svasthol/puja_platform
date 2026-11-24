"""Launch service boundary polygon (§21.13)."""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from fastapi import HTTPException

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
    from sqlalchemy import text

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