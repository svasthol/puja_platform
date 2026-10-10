"""Catalog + available pujaris (customer app). C-PUJAS / C-PUJARIS — Wave 4."""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status as http
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import Principal, require_customer
from app.db.engine import get_db
from app.schemas.catalog_customer import (
    CustomerPujaDetail,
    CustomerPujaListResponse,
    CustomerPujariListResponse,
)
from app.schemas.common import decode_cursor, encode_cursor
from app.services.catalog_read import (
    build_puja_detail,
    build_puja_summaries,
    list_customer_categories,
)
from app.services.pricing_resolver import resolve_puja_unit_price

router = APIRouter(tags=["catalog"])


@router.get("/pujas", response_model=CustomerPujaListResponse)
async def list_pujas(
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=50),
    category_id: int | None = None,
    locale: str = Query("te", pattern="^(te|en)$"),
    _p: Principal = Depends(require_customer),
    db: AsyncSession = Depends(get_db),
):
    """Active catalogue with categories, price ranges, and hero images."""
    categories = await list_customer_categories(db, locale=locale)

    params: dict = {"lim": limit + 1}
    filters = (
        "WHERE p.is_active "
        "AND EXISTS ("
        "  SELECT 1 FROM pujari_pricing pp "
        "  JOIN pujaris pj ON pj.id = pp.pujari_id "
        "  WHERE pp.puja_id = p.id AND pj.verification_status = 'verified'"
        ") "
    )
    if category_id is not None:
        params["cat"] = category_id
        filters += "AND p.category_id = :cat "

    cursor_pred = ""
    if cursor:
        order_str, id_str = decode_cursor(cursor, 2)
        try:
            params["c_order"] = int(order_str)
            params["c_id"] = uuid.UUID(id_str)
        except ValueError:
            raise HTTPException(http.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid cursor.")
        cursor_pred = "AND (p.display_order, p.id) > (:c_order, :c_id) "

    rows = (
        await db.execute(
            text(
                "SELECT p.id, p.category_id, p.name, p.slug, p.tagline, "
                "p.duration_minutes, p.default_price, p.display_order, p.hero_media_id, "
                "p.is_muhurat_bound "
                "FROM pujas p "
                + filters
                + cursor_pred
                + "ORDER BY p.display_order, p.id LIMIT :lim"
            ),
            params,
        )
    ).mappings().all()

    next_cursor = None
    page_rows = list(rows)
    if len(page_rows) > limit:
        page_rows = page_rows[:limit]
        last = page_rows[-1]
        next_cursor = encode_cursor(last["display_order"], last["id"])

    pujas = await build_puja_summaries(db, page_rows, locale=locale)
    return CustomerPujaListResponse(
        categories=categories,
        pujas=pujas,
        next_cursor=next_cursor,
    )


@router.get("/pujas/{puja_id}", response_model=CustomerPujaDetail)
async def get_puja(
    puja_id: uuid.UUID,
    locale: str = Query("te", pattern="^(te|en)$"),
    _p: Principal = Depends(require_customer),
    db: AsyncSession = Depends(get_db),
):
    """Puja detail — content blocks, addons, and gallery (ready media only)."""
    detail = await build_puja_detail(db, puja_id, locale=locale)
    if detail is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "Puja not found.")
    return CustomerPujaDetail(**detail)


@router.get("/pujaris", response_model=CustomerPujariListResponse)
async def available_pujaris(
    puja_id: uuid.UUID,
    date: dt.date,
    time: dt.time,
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=50),
    _p: Principal = Depends(require_customer),
    db: AsyncSession = Depends(get_db),
):
    """Verified pujaris priced via pricing_resolver for the puja + slot."""
    dow = date.weekday()
    params: dict = {"puja": str(puja_id), "dow": dow, "t": time, "d": date, "lim": limit + 1}
    cursor_pred = ""
    if cursor:
        ra_str, rc_str, id_str = decode_cursor(cursor, 3)
        try:
            params["c_ra"] = ra_str
            params["c_rc"] = int(rc_str)
            params["c_id"] = uuid.UUID(id_str)
        except ValueError:
            raise HTTPException(http.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid cursor.")
        cursor_pred = (
            "AND (pj.rating_avg, pj.rating_count, pj.id) "
            "< (CAST(:c_ra AS numeric), :c_rc, :c_id) "
        )
    rows = (
        await db.execute(
            text(
                """
                SELECT pj.id, pj.rating_avg, pj.rating_count, pj.years_experience
                FROM pujaris pj
                JOIN pujari_pricing pp ON pp.pujari_id = pj.id AND pp.puja_id = :puja
                WHERE pj.verification_status = 'verified'
                  AND EXISTS (
                    SELECT 1 FROM pujari_availability pa
                    WHERE pa.pujari_id = pj.id AND pa.day_of_week = :dow
                      AND pa.start_time <= :t AND pa.end_time > :t)
                  AND NOT EXISTS (
                    SELECT 1 FROM pujari_unavailability pu
                    WHERE pu.pujari_id = pj.id AND pu.unavailable_date = :d)
                  AND NOT EXISTS (
                    SELECT 1 FROM bookings b
                    WHERE b.pujari_id = pj.id AND b.cancelled_at IS NULL
                      AND b.scheduled_date = :d
                      AND tsrange(b.scheduled_date + b.scheduled_time,
                                  b.scheduled_date + b.scheduled_time
                                  + make_interval(mins => b.duration_minutes))
                          @> (:d + :t))
                """
                + cursor_pred
                + "ORDER BY pj.rating_avg DESC, pj.rating_count DESC, pj.id DESC LIMIT :lim"
            ),
            params,
        )
    ).mappings().all()

    next_cursor = None
    page_rows = list(rows)
    if len(page_rows) > limit:
        page_rows = page_rows[:limit]
        last = page_rows[-1]
        next_cursor = encode_cursor(last["rating_avg"], last["rating_count"], last["id"])

    pujaris = []
    for r in page_rows:
        pid = r["id"] if isinstance(r["id"], uuid.UUID) else uuid.UUID(str(r["id"]))
        unit_price = await resolve_puja_unit_price(db, puja_id, None)
        pujaris.append(
            {
                "id": pid,
                "rating_avg": Decimal(str(r["rating_avg"])),
                "rating_count": int(r["rating_count"]),
                "years_experience": r["years_experience"],
                "unit_price": unit_price,
            }
        )

    return CustomerPujariListResponse(pujaris=pujaris, next_cursor=next_cursor)
