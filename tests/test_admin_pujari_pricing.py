"""Sprint 4B — admin pujari pricing tests (A-PUJARI-PRICING)."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.api.v1.endpoints import admin_pujaris as pj_ep
from app.core.dependencies import Principal
from app.schemas.admin_pujaris import PujariPricingItemInput, PujariPricingReplaceRequest
from app.services.pricing_resolver import resolve_puja_unit_price


class _FakeRequest:
    client = None


def _admin(uid: uuid.UUID) -> Principal:
    return Principal(user_id=uid, app_context="admin", roles=("admin",))


async def _mk_admin(session) -> uuid.UUID:
    uid = uuid.uuid4()
    await session.execute(
        text("INSERT INTO users (id, full_name, phone) VALUES (:id, 'Admin', :ph)"),
        {"id": str(uid), "ph": "+91955" + uuid.uuid4().hex[:7]},
    )
    return uid


async def _mk_pujari(session) -> uuid.UUID:
    uid = uuid.uuid4()
    pid = uuid.uuid4()
    await session.execute(
        text("INSERT INTO users (id, full_name, phone) VALUES (:id, 'Pujari', :ph)"),
        {"id": str(uid), "ph": "+91956" + uuid.uuid4().hex[:7]},
    )
    await session.execute(
        text(
            "INSERT INTO pujaris (id, user_id, verification_status, created_at, updated_at) "
            "VALUES (:pid, :uid, 'verified', now(), now())"
        ),
        {"pid": str(pid), "uid": str(uid)},
    )
    return pid


@pytest.mark.asyncio
async def test_list_pujaris_search(session):
    actor = await _mk_admin(session)
    pid = await _mk_pujari(session)
    await session.commit()

    listed = await pj_ep.list_pujaris(limit=20, _p=_admin(actor), db=session)
    assert any(p.id == pid for p in listed.pujaris)


@pytest.mark.asyncio
async def test_replace_pujari_pricing(session):
    actor = await _mk_admin(session)
    pujari_id = await _mk_pujari(session)
    puja_id = (
        await session.execute(text("SELECT id FROM pujas WHERE is_active LIMIT 1"))
    ).scalar_one()
    await session.commit()

    new_price = Decimal("2500.00")
    result = await pj_ep.replace_pujari_pricing(
        pujari_id,
        PujariPricingReplaceRequest(
            items=[PujariPricingItemInput(puja_id=puja_id, base_price=new_price)],
            change_reason="test",
        ),
        _FakeRequest(),
        p=_admin(actor),
        db=session,
    )
    await session.commit()

    row = next(i for i in result.items if i.puja_id == puja_id)
    assert row.base_price == new_price

    resolved = await resolve_puja_unit_price(session, puja_id, pujari_id)
    assert resolved == new_price


@pytest.mark.asyncio
async def test_replace_pricing_rejects_above_price_max(session):
    actor = await _mk_admin(session)
    pujari_id = await _mk_pujari(session)
    puja_id = uuid.uuid4()
    cat_id = (await session.execute(text("SELECT id FROM puja_categories LIMIT 1"))).scalar_one()
    await session.execute(
        text(
            "INSERT INTO pujas (id, category_id, name, default_price, price_max, duration_minutes, is_active, "
            "created_at, updated_at) VALUES (:id, :cat, 'Max Test', 1000, 1200, 60, true, now(), now())"
        ),
        {"id": str(puja_id), "cat": cat_id},
    )
    await session.commit()

    with pytest.raises(HTTPException) as exc:
        await pj_ep.replace_pujari_pricing(
            pujari_id,
            PujariPricingReplaceRequest(
                items=[PujariPricingItemInput(puja_id=puja_id, base_price=Decimal("1500"))],
            ),
            _FakeRequest(),
            p=_admin(actor),
            db=session,
        )
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_get_pricing_matrix(session):
    actor = await _mk_admin(session)
    pujari_id = await _mk_pujari(session)
    await session.commit()

    matrix = await pj_ep.get_pujari_pricing(pujari_id, _p=_admin(actor), db=session)
    assert matrix.pujari_id == pujari_id
    assert len(matrix.items) >= 1
    assert matrix.items[0].puja_name
