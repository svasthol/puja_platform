"""Single source of truth for puja unit pricing (SPEC_AMENDMENTS §20.3).

Launch (broadcast): customer catalogue, quote, and booking use admin catalog
``pujas.default_price``. ``pujari_pricing`` is for dispatch supply and future
direct booking — not customer-facing display at launch.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def resolve_puja_unit_price(
    db: AsyncSession,
    puja_id: uuid.UUID,
    pujari_id: uuid.UUID | None = None,
) -> Decimal:
    """Unit price for one puja at checkout.

    direct (pujari_id present):
        COALESCE(pujari_pricing.base_price, pujas.default_price)
    broadcast (pujari_id absent):
        pujas.default_price
    """
    if pujari_id is not None:
        row = (
            await db.execute(
                text(
                    "SELECT COALESCE(pp.base_price, p.default_price) AS unit_price "
                    "FROM pujas p "
                    "LEFT JOIN pujari_pricing pp "
                    "  ON pp.pujari_id = :pid AND pp.puja_id = p.id "
                    "WHERE p.id = :puja"
                ),
                {"pid": str(pujari_id), "puja": str(puja_id)},
            )
        ).mappings().first()
    else:
        row = (
            await db.execute(
                text("SELECT default_price AS unit_price FROM pujas WHERE id = :puja"),
                {"puja": str(puja_id)},
            )
        ).mappings().first()

    if row is None:
        raise ValueError(f"Puja not found: {puja_id}")
    return Decimal(str(row["unit_price"]))


async def resolve_catalog_display_range(
    db: AsyncSession,
    puja_id: uuid.UUID,
) -> tuple[Decimal, Decimal]:
    """Customer-facing price range for catalogue cards (launch broadcast).

    price_from = resolve_puja_unit_price(pujari_id=None) — same as checkout
    price_to   = pujas.price_max OR price_from (display upper bound only)
    """
    row = (
        await db.execute(
            text(
                "SELECT default_price, price_max FROM pujas WHERE id = :puja"
            ),
            {"puja": str(puja_id)},
        )
    ).mappings().first()
    if row is None:
        raise ValueError(f"Puja not found: {puja_id}")

    price_from = await resolve_puja_unit_price(db, puja_id, None)
    price_to = (
        Decimal(str(row["price_max"])) if row["price_max"] is not None else price_from
    )
    if price_to < price_from:
        price_to = price_from
    return price_from, price_to
