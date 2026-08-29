"""Sprint 4B Wave 2 — catalogue media presign/confirm tests."""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.api.v1.endpoints import admin_catalog as cat_ep
from app.core.dependencies import Principal
from app.schemas.catalog_admin import MediaPresignRequest, PujaCreate
from app.services.catalog_media import CatalogMediaError


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
async def test_presign_and_confirm_media(session):
    actor = await _mk_user(session, "+91966" + uuid.uuid4().hex[:7])
    await session.commit()
    cat_id = await _category_id(session)

    puja = await cat_ep.create_puja(
        PujaCreate(category_id=cat_id, name=f"P-{uuid.uuid4().hex[:6]}", default_price=500),
        _FakeRequest(),
        p=_admin(actor),
        db=session,
    )
    await session.commit()

    presign_payload = MediaPresignRequest(
        entity_type="puja",
        entity_id=puja.id,
        content_type="image/png",
        content_length=1024,
        alt_text="Hero",
    )

    with patch(
        "app.api.v1.endpoints.admin_catalog.presign_catalog_put",
        return_value=("https://s3.example/upload", 600),
    ):
        presign = await cat_ep.presign_media(
            presign_payload,
            _FakeRequest(),
            p=_admin(actor),
            db=session,
        )
    await session.commit()

    assert presign.upload_url.startswith("https://")
    assert presign.upload_headers["Content-Type"] == "image/png"
    assert presign.s3_key.startswith("catalog/puja/")

    with patch(
        "app.api.v1.endpoints.admin_catalog.head_catalog_object",
        return_value={"content_length": 1024, "content_type": "image/png"},
    ):
        confirmed = await cat_ep.confirm_media(
            presign.media_id,
            _FakeRequest(),
            p=_admin(actor),
            db=session,
        )
    await session.commit()

    assert confirmed.upload_status == "ready"
    assert confirmed.is_active is True
    assert confirmed.confirmed_at is not None

    listed = await cat_ep.list_media(
        entity_type="puja",
        entity_id=puja.id,
        _p=_admin(actor),
        db=session,
    )
    assert len(listed.items) == 1
    assert listed.items[0].id == presign.media_id


@pytest.mark.asyncio
async def test_confirm_media_missing_object_returns_422(session):
    actor = await _mk_user(session, "+91966" + uuid.uuid4().hex[:7])
    await session.commit()
    cat_id = await _category_id(session)

    puja = await cat_ep.create_puja(
        PujaCreate(category_id=cat_id, name=f"P-{uuid.uuid4().hex[:6]}", default_price=500),
        _FakeRequest(),
        p=_admin(actor),
        db=session,
    )
    await session.commit()

    with patch(
        "app.api.v1.endpoints.admin_catalog.presign_catalog_put",
        return_value=("https://s3.example/upload", 600),
    ):
        presign = await cat_ep.presign_media(
            MediaPresignRequest(
                entity_type="gallery",
                entity_id=puja.id,
                content_type="image/jpeg",
                content_length=2048,
            ),
            _FakeRequest(),
            p=_admin(actor),
            db=session,
        )
    await session.commit()

    with patch(
        "app.api.v1.endpoints.admin_catalog.head_catalog_object",
        side_effect=CatalogMediaError("Object not found in storage."),
    ):
        with pytest.raises(HTTPException) as exc:
            await cat_ep.confirm_media(
                presign.media_id,
                _FakeRequest(),
                p=_admin(actor),
                db=session,
            )
    assert exc.value.status_code == 422
    await session.rollback()


@pytest.mark.asyncio
async def test_confirm_media_idempotent_when_ready(session):
    actor = await _mk_user(session, "+91966" + uuid.uuid4().hex[:7])
    await session.commit()
    cat_id = await _category_id(session)

    puja = await cat_ep.create_puja(
        PujaCreate(category_id=cat_id, name=f"P-{uuid.uuid4().hex[:6]}", default_price=500),
        _FakeRequest(),
        p=_admin(actor),
        db=session,
    )
    await session.commit()

    with patch(
        "app.api.v1.endpoints.admin_catalog.presign_catalog_put",
        return_value=("https://s3.example/upload", 600),
    ):
        presign = await cat_ep.presign_media(
            MediaPresignRequest(
                entity_type="puja",
                entity_id=puja.id,
                content_type="image/png",
                content_length=512,
            ),
            _FakeRequest(),
            p=_admin(actor),
            db=session,
        )
    await session.commit()

    with patch(
        "app.api.v1.endpoints.admin_catalog.head_catalog_object",
        return_value={"content_length": 512, "content_type": "image/png"},
    ):
        first = await cat_ep.confirm_media(
            presign.media_id, _FakeRequest(), p=_admin(actor), db=session
        )
        await session.commit()
        second = await cat_ep.confirm_media(
            presign.media_id, _FakeRequest(), p=_admin(actor), db=session
        )
    assert first.upload_status == "ready"
    assert second.upload_status == "ready"


@pytest.mark.asyncio
async def test_upload_media_proxy(session):
    actor = await _mk_user(session, "+91966" + uuid.uuid4().hex[:7])
    await session.commit()
    cat_id = await _category_id(session)

    puja = await cat_ep.create_puja(
        PujaCreate(category_id=cat_id, name=f"P-{uuid.uuid4().hex[:6]}", default_price=500),
        _FakeRequest(),
        p=_admin(actor),
        db=session,
    )
    await session.commit()

    with patch(
        "app.api.v1.endpoints.admin_catalog.presign_catalog_put",
        return_value=("https://s3.example/upload", 600),
    ):
        presign = await cat_ep.presign_media(
            MediaPresignRequest(
                entity_type="puja",
                entity_id=puja.id,
                content_type="image/png",
                content_length=100,
            ),
            _FakeRequest(),
            p=_admin(actor),
            db=session,
        )
    await session.commit()

    class _Req:
        client = None

        async def body(self):
            return b"\x89PNG fake"

        @property
        def headers(self):
            return {"content-type": "image/png"}

    with patch("app.api.v1.endpoints.admin_catalog.put_catalog_object"):
        await cat_ep.upload_media_body(
            presign.media_id,
            _Req(),
            p=_admin(actor),
            db=session,
        )
    await session.commit()


@pytest.mark.asyncio
async def test_presign_unknown_puja_404(session):
    actor = await _mk_user(session, "+91966" + uuid.uuid4().hex[:7])
    await session.commit()

    with patch(
        "app.api.v1.endpoints.admin_catalog.presign_catalog_put",
        return_value=("https://s3.example/upload", 600),
    ):
        with pytest.raises(HTTPException) as exc:
            await cat_ep.presign_media(
                MediaPresignRequest(
                    entity_type="puja",
                    entity_id=uuid.uuid4(),
                    content_type="image/webp",
                    content_length=512,
                ),
                _FakeRequest(),
                p=_admin(actor),
                db=session,
            )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_presign_addon_media(session):
    from app.schemas.catalog_admin import PujaAddonCreate

    actor = await _mk_user(session, "+91966" + uuid.uuid4().hex[:7])
    await session.commit()
    cat_id = await _category_id(session)

    puja = await cat_ep.create_puja(
        PujaCreate(category_id=cat_id, name=f"P-{uuid.uuid4().hex[:6]}", default_price=500),
        _FakeRequest(),
        p=_admin(actor),
        db=session,
    )
    addon = await cat_ep.create_addon(
        puja.id,
        PujaAddonCreate(name="Samagri pack", price=300),
        _FakeRequest(),
        p=_admin(actor),
        db=session,
    )
    await session.commit()

    with patch(
        "app.api.v1.endpoints.admin_catalog.presign_catalog_put",
        return_value=("https://s3.example/upload", 600),
    ):
        presign = await cat_ep.presign_media(
            MediaPresignRequest(
                entity_type="addon",
                entity_id=addon.id,
                content_type="image/webp",
                content_length=2048,
                alt_text="Addon thumb",
            ),
            _FakeRequest(),
            p=_admin(actor),
            db=session,
        )
    await session.commit()

    assert presign.s3_key.startswith("catalog/addon/")
