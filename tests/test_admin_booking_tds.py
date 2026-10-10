"""Admin booking TDS read-only snapshot."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.api.v1.endpoints import admin_bookings as admin_bookings_ep
from app.core.dependencies import Principal


class _FakeRequest:
    client = None


async def _mk_admin(session) -> Principal:
    uid = uuid.uuid4()
    await session.execute(
        text("INSERT INTO users (id, full_name, phone) VALUES (:id, 'A', :ph)"),
        {"id": str(uid), "ph": "+91990" + uuid.uuid4().hex[:7]},
    )
    return Principal(user_id=uid, app_context="admin", roles=("admin",))


@pytest.mark.asyncio
async def test_booking_tds_snapshot(session, seed):
    admin = await _mk_admin(session)
    bid = uuid.uuid4()
    row = (
        await session.execute(
            text("SELECT id FROM bookings LIMIT 1"),
        )
    ).scalar_one_or_none()
    if row is None:
        pytest.skip("no bookings in seed")
    bid = uuid.UUID(str(row))
    resp = await admin_bookings_ep.get_booking_tds(
        bid, _FakeRequest(), admin, session
    )
    assert resp.booking_id == bid
    assert isinstance(resp.hints, list)
