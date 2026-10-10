"""Launch catalog pricing — admin default is single customer-facing source (broadcast)."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.api.v1.endpoints import bookings as bookings_ep
from app.api.v1.endpoints import catalog as cat_ep
from app.core.dependencies import Principal
from app.services import booking_service
from app.services.pricing_resolver import resolve_catalog_display_range, resolve_puja_unit_price


def _customer(uid: uuid.UUID) -> Principal:
    return Principal(user_id=uid, app_context="customer", roles=())


async def _seed_launch_puja_with_cheaper_pujari(
    session,
    *,
    default_price: Decimal = Decimal("2500.00"),
    pujari_base: Decimal = Decimal("1800.00"),
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Puja with catalog default higher than verified pujari_pricing (no promo, no addons)."""
    customer_id = uuid.uuid4()
    puja_id = uuid.uuid4()
    pujari_id = uuid.uuid4()
    user_id = uuid.uuid4()
    cat_id = (await session.execute(text("SELECT id FROM puja_categories LIMIT 1"))).scalar_one()

    await session.execute(
        text("INSERT INTO users (id, full_name, phone) VALUES (:id, 'C', :ph)"),
        {"id": str(customer_id), "ph": "+91981" + uuid.uuid4().hex[:7]},
    )
    await session.execute(
        text("INSERT INTO users (id, full_name, phone) VALUES (:id, 'P', :ph)"),
        {"id": str(user_id), "ph": "+91982" + uuid.uuid4().hex[:7]},
    )
    await session.execute(
        text(
            "INSERT INTO pujaris (id, user_id, verification_status, created_at, updated_at) "
            "VALUES (:p, :u, 'verified', now(), now())"
        ),
        {"p": str(pujari_id), "u": str(user_id)},
    )
    slug = f"launch-price-{uuid.uuid4().hex[:8]}"
    await session.execute(
        text(
            "INSERT INTO pujas (id, category_id, name, slug, default_price, duration_minutes, "
            "is_active, display_order, created_at, updated_at) "
            "VALUES (:id, :cat, 'Launch Price Puja', :slug, :dp, 60, true, 0, now(), now())"
        ),
        {
            "id": str(puja_id),
            "cat": cat_id,
            "slug": slug,
            "dp": str(default_price),
        },
    )
    await session.execute(
        text(
            "INSERT INTO pujari_pricing (id, pujari_id, puja_id, base_price) "
            "VALUES (:id, :pid, :puja, :bp)"
        ),
        {
            "id": str(uuid.uuid4()),
            "pid": str(pujari_id),
            "puja": str(puja_id),
            "bp": str(pujari_base),
        },
    )
    await session.commit()
    return customer_id, puja_id, pujari_id


@pytest.mark.asyncio
async def test_catalog_display_ignores_lower_pujari_pricing(session):
    _, puja_id, _ = await _seed_launch_puja_with_cheaper_pujari(session)
    price_from, price_to = await resolve_catalog_display_range(session, puja_id)
    unit = await resolve_puja_unit_price(session, puja_id, None)
    assert price_from == Decimal("2500.00")
    assert price_to == Decimal("2500.00")
    assert unit == price_from


@pytest.mark.asyncio
async def test_launch_pricing_single_source_across_api_and_booking(session):
    """No promo, no addons — puja line must match catalog default everywhere."""
    customer_id, puja_id, _ = await _seed_launch_puja_with_cheaper_pujari(session)
    expected = Decimal("2500.00")

    price_from, _ = await resolve_catalog_display_range(session, puja_id)
    unit = await resolve_puja_unit_price(session, puja_id, None)
    assert price_from == expected
    assert unit == expected

    detail = await cat_ep.get_puja(
        puja_id, locale="en", _p=_customer(customer_id), db=session
    )
    assert detail.price_from == expected
    assert detail.default_price == expected

    quote = await bookings_ep.checkout_quote(
        puja_id=puja_id,
        pujari_id=None,
        addon_ids=[],
        _p=_customer(customer_id),
        db=session,
    )
    assert quote.total_amount == expected

    total, _, _, _ = await booking_service.compute_amounts(
        session,
        puja_id=puja_id,
        pujari_id=None,
        addon_prices=[],
        promo_pct=0,
        payment_mode="booking_fee",
    )
    assert total == expected
