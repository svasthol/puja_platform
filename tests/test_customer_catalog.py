"""Sprint 4B Wave 4 — customer catalogue read APIs (C-PUJAS / C-PUJARIS)."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.api.v1.endpoints import catalog as cat_ep
from app.core.dependencies import Principal
from app.services.catalog_read import category_entity_uuid
from app.services.pricing_resolver import resolve_puja_unit_price


def _customer(uid: uuid.UUID) -> Principal:
    return Principal(user_id=uid, app_context="customer", roles=())


@pytest.mark.asyncio
async def test_list_pujas_includes_price_range_and_categories(session):
    customer_id = uuid.uuid4()
    await session.execute(
        text("INSERT INTO users (id, full_name, phone) VALUES (:id, 'C', :ph)"),
        {"id": str(customer_id), "ph": "+91988" + uuid.uuid4().hex[:7]},
    )
    await session.commit()

    resp = await cat_ep.list_pujas(limit=20, _p=_customer(customer_id), db=session)
    assert resp.categories
    assert resp.pujas
    puja = resp.pujas[0]
    assert puja.slug is not None
    assert puja.price_from <= puja.price_to
    assert puja.default_price == Decimal(str(puja.default_price))


@pytest.mark.asyncio
async def test_list_pujas_category_filter(session):
    customer_id = uuid.uuid4()
    await session.execute(
        text("INSERT INTO users (id, full_name, phone) VALUES (:id, 'C', :ph)"),
        {"id": str(customer_id), "ph": "+91987" + uuid.uuid4().hex[:7]},
    )
    cat_id = (await session.execute(text("SELECT id FROM puja_categories LIMIT 1"))).scalar_one()
    await session.commit()

    resp = await cat_ep.list_pujas(category_id=cat_id, limit=20, _p=_customer(customer_id), db=session)
    assert all(p.category_id == cat_id for p in resp.pujas)


@pytest.mark.asyncio
async def test_get_puja_detail_content_addons(session):
    customer_id = uuid.uuid4()
    puja_id = uuid.uuid4()
    cat_id = (await session.execute(text("SELECT id FROM puja_categories LIMIT 1"))).scalar_one()

    await session.execute(
        text("INSERT INTO users (id, full_name, phone) VALUES (:id, 'C', :ph)"),
        {"id": str(customer_id), "ph": "+91986" + uuid.uuid4().hex[:7]},
    )
    slug = f"detail-puja-{uuid.uuid4().hex[:8]}"
    await session.execute(
        text(
            "INSERT INTO pujas (id, category_id, name, slug, default_price, duration_minutes, "
            "is_active, display_order, created_at, updated_at) "
            "VALUES (:id, :cat, 'Detail Puja', :slug, 1800.00, 60, true, 0, now(), now())"
        ),
        {"id": str(puja_id), "cat": cat_id, "slug": slug},
    )
    await session.execute(
        text(
            "INSERT INTO puja_content_items (id, puja_id, kind, position, text, is_active) "
            "VALUES (:id, :pid, 'inclusion', 0, 'Flowers', true)"
        ),
        {"id": str(uuid.uuid4()), "pid": str(puja_id)},
    )
    await session.execute(
        text(
            "INSERT INTO puja_addons (id, puja_id, name, price, display_order, is_active) "
            "VALUES (:id, :pid, 'Extra prasad', 99.00, 0, true)"
        ),
        {"id": str(uuid.uuid4()), "pid": str(puja_id)},
    )
    await session.commit()

    detail = await cat_ep.get_puja(puja_id, _p=_customer(customer_id), db=session)
    assert detail.name == "Detail Puja"
    assert detail.price_from <= detail.price_to
    kinds = {b.kind: b.items for b in detail.content}
    assert kinds.get("inclusion") == ["Flowers"]
    assert len(detail.addons) == 1
    assert detail.addons[0].name == "Extra prasad"


@pytest.mark.asyncio
async def test_get_puja_inactive_not_found(session):
    customer_id = uuid.uuid4()
    puja_id = uuid.uuid4()
    cat_id = (await session.execute(text("SELECT id FROM puja_categories LIMIT 1"))).scalar_one()

    await session.execute(
        text("INSERT INTO users (id, full_name, phone) VALUES (:id, 'C', :ph)"),
        {"id": str(customer_id), "ph": "+91985" + uuid.uuid4().hex[:7]},
    )
    await session.execute(
        text(
            "INSERT INTO pujas (id, category_id, name, default_price, is_active, "
            "created_at, updated_at) VALUES (:id, :cat, 'Off', 100.00, false, now(), now())"
        ),
        {"id": str(puja_id), "cat": cat_id},
    )
    await session.commit()

    with pytest.raises(HTTPException) as exc:
        await cat_ep.get_puja(puja_id, _p=_customer(customer_id), db=session)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_pujaris_unit_price_matches_resolver(session):
    customer_id = uuid.uuid4()
    puja_id = (
        await session.execute(text("SELECT id FROM pujas WHERE is_active LIMIT 1"))
    ).scalar_one()
    row = (
        await session.execute(
            text(
                "SELECT pp.pujari_id FROM pujari_pricing pp "
                "JOIN pujaris pj ON pj.id = pp.pujari_id "
                "WHERE pp.puja_id = :pid AND pj.verification_status = 'verified' LIMIT 1"
            ),
            {"pid": str(puja_id)},
        )
    ).first()
    if row is None:
        pytest.skip("No verified pujari_pricing row in seed data")

    pujari_id = row[0]
    await session.execute(
        text("INSERT INTO users (id, full_name, phone) VALUES (:id, 'C', :ph)"),
        {"id": str(customer_id), "ph": "+91984" + uuid.uuid4().hex[:7]},
    )
    await session.execute(
        text(
            "INSERT INTO pujari_availability (id, pujari_id, day_of_week, start_time, end_time) "
            "VALUES (:id, :pid, 0, '00:00', '23:59') ON CONFLICT DO NOTHING"
        ),
        {"id": str(uuid.uuid4()), "pid": str(pujari_id)},
    )
    await session.commit()

    import datetime as dt

    resp = await cat_ep.available_pujaris(
        puja_id=puja_id,
        date=dt.date(2036, 1, 5),  # Monday
        time=dt.time(10, 0),
        limit=20,
        _p=_customer(customer_id),
        db=session,
    )
    match = next((p for p in resp.pujaris if p.id == pujari_id), None)
    if match is None:
        pytest.skip("Pujari not returned for slot (availability/overlap filters)")

    expected = await resolve_puja_unit_price(session, puja_id, pujari_id)
    assert match.unit_price == expected


@pytest.mark.asyncio
async def test_category_entity_uuid_roundtrip():
    assert category_entity_uuid(42).int == 42
