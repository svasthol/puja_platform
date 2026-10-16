"""Pricing resolver tests — Sprint 4B Wave-0 (SPEC_AMENDMENTS §20.3)."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.services.pricing_resolver import resolve_catalog_display_range, resolve_puja_unit_price


@pytest.mark.asyncio
async def test_resolve_unit_price_broadcast_uses_default(session):
    puja_id = (
        await session.execute(text("SELECT id FROM pujas LIMIT 1"))
    ).scalar_one()
    price = await resolve_puja_unit_price(session, puja_id, None)
    default = (
        await session.execute(
            text("SELECT default_price FROM pujas WHERE id = :id"), {"id": str(puja_id)}
        )
    ).scalar_one()
    assert price == Decimal(str(default))


@pytest.mark.asyncio
async def test_resolve_unit_price_direct_uses_pujari_pricing(session):
    row = (
        await session.execute(
            text(
                "SELECT pp.pujari_id, pp.puja_id, pp.base_price "
                "FROM pujari_pricing pp LIMIT 1"
            )
        )
    ).mappings().first()
    if row is None:
        pytest.skip("No pujari_pricing row in seed data")

    price = await resolve_puja_unit_price(
        session, row["puja_id"], row["pujari_id"]
    )
    assert price == Decimal(str(row["base_price"]))


@pytest.mark.asyncio
async def test_resolve_unit_price_direct_falls_back_to_default(session):
    user_id = uuid.uuid4()
    pujari_id = uuid.uuid4()
    puja_id = uuid.uuid4()
    await session.execute(
        text("INSERT INTO users (id, full_name, phone) VALUES (:u, 'T', :ph)"),
        {"u": str(user_id), "ph": "+91977" + uuid.uuid4().hex[:7]},
    )
    await session.execute(
        text(
            "INSERT INTO pujaris (id, user_id, created_at, updated_at) "
            "VALUES (:p, :u, now(), now())"
        ),
        {"p": str(pujari_id), "u": str(user_id)},
    )
    cat_id = (
        await session.execute(text("SELECT id FROM puja_categories LIMIT 1"))
    ).scalar_one()
    await session.execute(
        text(
            "INSERT INTO pujas (id, category_id, name, default_price, duration_minutes, is_active) "
            "VALUES (:id, :cat, 'Resolver Test', 2100.00, 90, true)"
        ),
        {"id": str(puja_id), "cat": cat_id},
    )
    await session.commit()

    price = await resolve_puja_unit_price(session, puja_id, pujari_id)
    assert price == Decimal("2100.00")


@pytest.mark.asyncio
async def test_resolve_display_range_matches_catalog_default(session):
    puja_id = (
        await session.execute(text("SELECT id FROM pujas LIMIT 1"))
    ).scalar_one()
    low, high = await resolve_catalog_display_range(session, puja_id)
    unit = await resolve_puja_unit_price(session, puja_id, None)
    assert low == unit
    assert low <= high


@pytest.mark.asyncio
async def test_resolve_display_range_uses_price_max(session):
    puja_id = uuid.uuid4()
    cat_id = (await session.execute(text("SELECT id FROM puja_categories LIMIT 1"))).scalar_one()
    await session.execute(
        text(
            "INSERT INTO pujas (id, category_id, name, default_price, price_max, "
            "duration_minutes, is_active, created_at, updated_at) "
            "VALUES (:id, :cat, 'Range Puja', 2000.00, 3500.00, 60, true, now(), now())"
        ),
        {"id": str(puja_id), "cat": cat_id},
    )
    await session.commit()
    low, high = await resolve_catalog_display_range(session, puja_id)
    assert low == Decimal("2000.00")
    assert high == Decimal("3500.00")
