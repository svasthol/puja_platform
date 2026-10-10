"""Admin TDS FY reconcile troubleshoot."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.api.v1.endpoints import admin_tds as admin_tds_ep
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
async def test_troubleshoot_unknown_pujari(session, seed):
    admin = await _mk_admin(session)
    with pytest.raises(Exception):
        await admin_tds_ep.get_fy_reconcile_troubleshoot(
            _FakeRequest(),
            uuid.uuid4(),
            None,
            admin,
            session,
        )


@pytest.mark.asyncio
async def test_troubleshoot_seed_pujari(session, seed):
    admin = await _mk_admin(session)
    pid = uuid.UUID("cccccccc-0000-0000-0000-000000000001")
    resp = await admin_tds_ep.get_fy_reconcile_troubleshoot(
        _FakeRequest(),
        pid,
        None,
        admin,
        session,
    )
    assert resp.pujari_id == pid
    assert resp.messages
    assert resp.tax.status in ("match", "fixable", "manual", "accrual_disabled")
