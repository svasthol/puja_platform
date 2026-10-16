"""Customer catalogue visibility rules (launch — Telugu te i18n required)."""
from __future__ import annotations

import uuid

from fastapi import HTTPException, status as http
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# SQL fragment for queries aliasing pujas as `p`.
CUSTOMER_PUJA_VISIBILITY_SQL = """
AND p.slug IS NOT NULL AND trim(p.slug) <> ''
AND EXISTS (
    SELECT 1 FROM puja_i18n i
    WHERE i.puja_id = p.id AND i.locale = 'te' AND trim(i.name) <> ''
)
AND EXISTS (
    SELECT 1 FROM pujari_pricing pp
    JOIN pujaris pj ON pj.id = pp.pujari_id
    WHERE pp.puja_id = p.id AND pj.verification_status = 'verified'
)
"""

CATALOG_INCOMPLETE_CODE = "CATALOG_INCOMPLETE_FOR_LAUNCH"


async def customer_puja_is_visible(db: AsyncSession, puja_id: uuid.UUID) -> bool:
    row = (
        await db.execute(
            text(
                "SELECT 1 FROM pujas p WHERE p.id = :id AND p.is_active "
                + CUSTOMER_PUJA_VISIBILITY_SQL
            ),
            {"id": str(puja_id)},
        )
    ).first()
    return row is not None


async def assert_puja_customer_launch_complete(db: AsyncSession, puja_id: uuid.UUID) -> None:
    """Raise 422 if puja cannot be shown on the customer catalogue."""
    slug_ok = (
        await db.execute(
            text(
                "SELECT 1 FROM pujas WHERE id = :id AND slug IS NOT NULL AND trim(slug) <> ''"
            ),
            {"id": str(puja_id)},
        )
    ).first()
    te_ok = (
        await db.execute(
            text(
                """
                SELECT 1 FROM puja_i18n
                WHERE puja_id = :id AND locale = 'te' AND trim(name) <> ''
                """
            ),
            {"id": str(puja_id)},
        )
    ).first()
    if slug_ok and te_ok:
        return
    raise HTTPException(
        http.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={
            "code": CATALOG_INCOMPLETE_CODE,
            "message": "Active catalogue requires non-empty slug and Telugu (te) puja name.",
        },
    )
