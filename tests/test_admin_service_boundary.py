"""Admin service boundary settings (§21.13, A-SERVICE-BOUNDARY)."""
from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.api.v1.endpoints import admin_service_boundary as sb_ep
from app.core.dependencies import Principal
from app.schemas.admin_service_boundary import ServiceBoundarySettingsUpdate
from app.schemas.serviceability import ServiceabilityProbeRequest


def _admin(uid: uuid.UUID) -> Principal:
    return Principal(user_id=uid, app_context="admin", roles=("admin",))


def _support(uid: uuid.UUID) -> Principal:
    return Principal(user_id=uid, app_context="admin", roles=("support",))


class _FakeRequest:
    client = None


async def _mk_admin(session) -> uuid.UUID:
    uid = uuid.uuid4()
    await session.execute(
        text("INSERT INTO users (id, full_name, phone) VALUES (:id, 'Admin', :ph)"),
        {"id": str(uid), "ph": "+91972" + uuid.uuid4().hex[:7]},
    )
    return uid


@pytest.mark.asyncio
async def test_get_service_boundary_disabled_by_default(session, seed):
    actor = await _mk_admin(session)
    await session.commit()
    resp = await sb_ep.get_service_boundary_settings(session, _admin(actor))
    assert resp.service_boundary_enabled is False


@pytest.mark.asyncio
async def test_support_can_read_service_boundary(session, seed):
    actor = await _mk_admin(session)
    await session.commit()
    resp = await sb_ep.get_service_boundary_settings(session, _support(actor))
    assert resp.service_boundary_enabled is False


@pytest.mark.asyncio
async def test_admin_enables_boundary_when_polygon_loaded(session, seed):
    actor = await _mk_admin(session)
    await session.commit()
    status = await sb_ep.service_boundary_status(session, _admin(actor))
    assert status.loaded is True

    updated = await sb_ep.update_service_boundary_settings(
        ServiceBoundarySettingsUpdate(
            service_boundary_enabled=True,
            change_reason="launch QA",
        ),
        _FakeRequest(),
        _admin(actor),
        session,
    )
    assert updated.service_boundary_enabled is True


@pytest.mark.asyncio
async def test_probe_inside_launch_rectangle(session, seed):
    await _mk_admin(session)
    await session.commit()
    resp = await sb_ep.service_boundary_probe(
        ServiceabilityProbeRequest(lat=17.4, lng=78.4),
        _admin(uuid.uuid4()),
    )
    assert resp.serviceable is True


@pytest.mark.asyncio
async def test_probe_outside_launch_rectangle(session, seed):
    await _mk_admin(session)
    await session.commit()
    resp = await sb_ep.service_boundary_probe(
        ServiceabilityProbeRequest(lat=19.076, lng=72.8777),
        _admin(uuid.uuid4()),
    )
    assert resp.serviceable is False
    assert resp.code is not None