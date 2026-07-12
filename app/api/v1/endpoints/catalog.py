"""Catalog + available pujaris (customer app). C-PUJAS / C-PUJARIS."""
from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status as http
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import Principal, require_customer
from app.db.engine import get_db
from app.models.lookups import PujaCategory
from app.schemas.common import decode_cursor, encode_cursor

router = APIRouter(tags=["catalog"])


@router.get("/pujas")
async def list_pujas(
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=50),
    _p: Principal = Depends(require_customer),
    db: AsyncSession = Depends(get_db),
):
    cats = (await db.execute(select(PujaCategory))).scalars().all()

    params: dict = {"lim": limit + 1}
    cursor_pred = ""
    if cursor:
        name_str, id_str = decode_cursor(cursor, 2)
        try:
            params["c_name"] = name_str
            params["c_id"] = uuid.UUID(id_str)
        except ValueError:
            raise HTTPException(http.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid cursor.")
        cursor_pred = "AND (p.name, p.id) > (:c_name, :c_id) "
    rows = (
        await db.execute(
            text(
                "SELECT p.id, p.category_id, p.name, p.duration_minutes, p.default_price "
                "FROM pujas p WHERE p.is_active "
                + cursor_pred
                + "ORDER BY p.name, p.id LIMIT :lim"
            ),
            params,
        )
    ).mappings().all()
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = encode_cursor(last["name"], last["id"])
    return {
        "categories": [{"id": c.id, "name": c.name} for c in cats],
        "pujas": [
            {
                "id": str(r["id"]),
                "category_id": r["category_id"],
                "name": r["name"],
                "duration_minutes": r["duration_minutes"],
                "default_price": str(r["default_price"]),
            }
            for r in rows
        ],
        "next_cursor": next_cursor,
    }


@router.get("/pujaris")
async def available_pujaris(
    puja_id: uuid.UUID,
    date: dt.date,
    time: dt.time,
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=50),
    _p: Principal = Depends(require_customer),
    db: AsyncSession = Depends(get_db),
):
    """Available = verified, prices this puja (pujari_pricing), availability
    covers slot, no unavailability that date, no overlapping active booking."""
    dow = date.weekday()  # 0=Mon..6=Sun; schema uses 0..6
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
                SELECT pj.id, pj.rating_avg, pj.rating_count, pj.years_experience,
                       pp.base_price
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
                          @> (:d::date + :t::time))
                """
                + cursor_pred
                + "ORDER BY pj.rating_avg DESC, pj.rating_count DESC, pj.id DESC LIMIT :lim"
            ),
            params,
        )
    ).mappings().all()
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = encode_cursor(last["rating_avg"], last["rating_count"], last["id"])
    return {"pujaris": [dict(r) for r in rows], "next_cursor": next_cursor}
