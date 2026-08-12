"""Sprint 4B Wave 1 — admin catalogue API tests."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.api.v1.endpoints import admin_catalog as cat_ep
from app.core.dependencies import Principal
from app.schemas.catalog_admin import (
    ContentItemInput,
    ContentReplaceRequest,
    PujaAddonCreate,
    PujaAddonUpdate,
    PujaCategoryCreate,
    PujaCategoryUpdate,
    PujaCreate,
    PujaUpdate,
    ReorderRequest,
)


class _FakeRequest:
    client = None


def _admin(uid: uuid.UUID) -> Principal:
    return Principal(user_id=uid, app_context="admin", roles=("admin",))


async def _mk_user(session, phone: str) -> uuid.UUID:
    uid = uuid.uuid4()
    await session.execute(
        text("INSERT INTO users (id, full_name, phone) VALUES (:id, 'T', :ph)"),
        {"id": str(uid), "ph": phone},
    )
    return uid


async def _category_id(session) -> int:
    return (await session.execute(text("SELECT id FROM puja_categories LIMIT 1"))).scalar_one()


@pytest.mark.asyncio
async def test_category_crud_and_reorder(session):
    actor = await _mk_user(session, "+91966" + uuid.uuid4().hex[:7])
    await session.commit()

    created = await cat_ep.create_category(
        PujaCategoryCreate(name=f"Cat-{uuid.uuid4().hex[:6]}"),
        _FakeRequest(),
        p=_admin(actor),
        db=session,
    )
    await session.commit()
    assert created.slug
    assert created.display_order >= 0

    updated = await cat_ep.update_category(
        created.id,
        PujaCategoryUpdate(description="Festivals", is_active=False),
        _FakeRequest(),
        p=_admin(actor),
        db=session,
    )
    await session.commit()
    assert updated.description == "Festivals"
    assert updated.is_active is False

    listed = await cat_ep.list_categories(_p=_admin(actor), db=session)
    ids = [c.id for c in listed.categories]
    reordered = list(reversed(ids[:3])) + ids[3:]
    await cat_ep.reorder_categories(
        ReorderRequest(ordered_ids=reordered),
        _FakeRequest(),
        p=_admin(actor),
        db=session,
    )
    await session.commit()
    after = await cat_ep.list_categories(_p=_admin(actor), db=session)
    assert [c.id for c in after.categories[:3]] == reordered[:3]


@pytest.mark.asyncio
async def test_puja_crud_impact_and_price_max_guard(session):
    actor = await _mk_user(session, "+91966" + uuid.uuid4().hex[:7])
    await session.commit()
    cat_id = await _category_id(session)

    puja = await cat_ep.create_puja(
        PujaCreate(
            category_id=cat_id,
            name=f"Puja-{uuid.uuid4().hex[:6]}",
            default_price=Decimal("1500"),
            price_max=Decimal("2500"),
            duration_minutes=90,
        ),
        _FakeRequest(),
        p=_admin(actor),
        db=session,
    )
    await session.commit()
    assert puja.slug

    impact = await cat_ep.puja_impact(puja.id, _p=_admin(actor), db=session)
    assert impact.puja_id == puja.id
    assert impact.active_future_bookings >= 0

    with pytest.raises(HTTPException) as exc:
        await cat_ep.update_puja(
            puja.id,
            PujaUpdate(default_price=Decimal("3000"), price_max=Decimal("2000")),
            _FakeRequest(),
            p=_admin(actor),
            db=session,
        )
    assert exc.value.status_code == 422
    await session.rollback()

    updated = await cat_ep.update_puja(
        puja.id,
        PujaUpdate(tagline="Blessings at home", is_active=True),
        _FakeRequest(),
        p=_admin(actor),
        db=session,
    )
    await session.commit()
    assert updated.tagline == "Blessings at home"


@pytest.mark.asyncio
async def test_content_replace_and_addons(session):
    actor = await _mk_user(session, "+91966" + uuid.uuid4().hex[:7])
    await session.commit()
    cat_id = await _category_id(session)

    puja = await cat_ep.create_puja(
        PujaCreate(category_id=cat_id, name=f"P-{uuid.uuid4().hex[:6]}", default_price=Decimal("500")),
        _FakeRequest(),
        p=_admin(actor),
        db=session,
    )
    await session.commit()

    content = await cat_ep.replace_content(
        puja.id,
        ContentReplaceRequest(
            kind="inclusion",
            items=[
                ContentItemInput(text="Flowers", position=0),
                ContentItemInput(text="Fruits", position=1),
            ],
        ),
        _FakeRequest(),
        p=_admin(actor),
        db=session,
    )
    await session.commit()
    assert len(content.items) == 2

    addon = await cat_ep.create_addon(
        puja.id,
        PujaAddonCreate(name="Extra diya", price=Decimal("99")),
        _FakeRequest(),
        p=_admin(actor),
        db=session,
    )
    await session.commit()

    updated_addon = await cat_ep.update_addon(
        addon.id,
        PujaAddonUpdate(description="Brass diya", is_active=False),
        _FakeRequest(),
        p=_admin(actor),
        db=session,
    )
    await session.commit()
    assert updated_addon.is_active is False

    addons = await cat_ep.list_addons(puja.id, _p=_admin(actor), db=session)
    assert len(addons.addons) == 1

    audit = (
        await session.execute(
            text(
                "SELECT count(*) FROM admin_audit_log "
                "WHERE actor_user_id = :a AND entity_type IN "
                "('pujas','puja_content_items','puja_addons')"
            ),
            {"a": str(actor)},
        )
    ).scalar_one()
    assert audit >= 4
