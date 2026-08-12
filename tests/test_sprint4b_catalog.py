"""Sprint 4B — A-CAT-CATEGORIES admin catalogue tests."""
from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.api.v1.endpoints import admin_catalog as cat_ep
from app.core.dependencies import Principal
from app.schemas.catalog_admin import PujaCategoryCreate, PujaCategoryUpdate


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


def _uniq_name() -> str:
    return f"Cat-{uuid.uuid4().hex[:8]}"


@pytest.mark.asyncio
async def test_create_list_update_category(session):
    actor = await _mk_user(session, "+91966" + uuid.uuid4().hex[:7])
    await session.commit()

    name = _uniq_name()
    created = await cat_ep.create_category(
        PujaCategoryCreate(name=name, change_reason="test"),
        _FakeRequest(),
        p=_admin(actor),
        db=session,
    )
    await session.commit()
    assert created.is_active is True

    listed = await cat_ep.list_categories(_p=_admin(actor), db=session)
    assert any(c.id == created.id for c in listed.categories)

    updated = await cat_ep.update_category(
        created.id,
        PujaCategoryUpdate(is_active=False, change_reason="retire"),
        _FakeRequest(),
        p=_admin(actor),
        db=session,
    )
    await session.commit()
    assert updated.is_active is False

    audit = (
        await session.execute(
            text(
                "SELECT action FROM admin_audit_log "
                "WHERE entity_type = 'puja_categories' AND entity_id = :e "
                "ORDER BY created_at"
            ),
            {"e": str(created.id)},
        )
    ).scalars().all()
    assert audit == ["create", "update"]


@pytest.mark.asyncio
async def test_duplicate_category_name_rejected(session):
    actor = await _mk_user(session, "+91966" + uuid.uuid4().hex[:7])
    await session.commit()
    name = _uniq_name()

    await cat_ep.create_category(
        PujaCategoryCreate(name=name), _FakeRequest(), p=_admin(actor), db=session
    )
    await session.commit()

    with pytest.raises(HTTPException) as exc:
        await cat_ep.create_category(
            PujaCategoryCreate(name=name), _FakeRequest(), p=_admin(actor), db=session
        )
    assert exc.value.status_code == 409
    await session.rollback()
