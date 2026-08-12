"""Public panchangam read API — server cache only (§23.6)."""
from __future__ import annotations

import asyncio
import datetime as dt
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status as http
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.schemas.panchangam import PanchangamResponse
from app.services.panchangam import fetch_panchangam, today_ist
from app.workers.panchangam import fetch_and_cache_panchangam
from app.workers.sweep import get_connection

router = APIRouter(tags=["panchangam"])

# Match worker backfill horizon — avoid vendor fetch for arbitrary future dates.
_ON_DEMAND_HORIZON_DAYS = 7


def _date_in_on_demand_horizon(panchang_date: dt.date) -> bool:
    today = today_ist()
    end = today + dt.timedelta(days=_ON_DEMAND_HORIZON_DAYS)
    return today <= panchang_date <= end


def _try_vendor_cache_fill(
    *,
    city: str,
    panchang_date: dt.date,
    locale: str,
    panchang_system: str,
) -> bool:
    """Sync vendor fetch on cache miss — keeps mobile on GET /v1/panchangam only."""
    conn = get_connection()
    try:
        return fetch_and_cache_panchangam(
            conn,
            city=city,
            panchang_date=panchang_date,
            locale=locale,
            panchang_system=panchang_system,
        )
    finally:
        conn.close()


@router.get("/panchangam", response_model=PanchangamResponse)
async def get_panchangam(
    city: str = Query(..., min_length=1, max_length=80),
    date: dt.date | None = Query(None, alias="date"),
    locale: Literal["te", "en"] = Query("te"),
    panchang_system: Literal["drik", "vakya"] = Query("drik"),
    db: AsyncSession = Depends(get_db),
):
    """Daily panchangam from server cache — mobile never calls vendor directly."""
    target_date = date or today_ist()
    result = await fetch_panchangam(
        db,
        city=city,
        panchang_date=target_date,
        locale=locale,
        panchang_system=panchang_system,
    )
    if result is None and _date_in_on_demand_horizon(target_date):
        filled = await asyncio.to_thread(
            _try_vendor_cache_fill,
            city=city,
            panchang_date=target_date,
            locale=locale,
            panchang_system=panchang_system,
        )
        if filled:
            result = await fetch_panchangam(
                db,
                city=city,
                panchang_date=target_date,
                locale=locale,
                panchang_system=panchang_system,
            )
    if result is None:
        raise HTTPException(
            http.HTTP_404_NOT_FOUND,
            "Panchangam not available for this city and date yet.",
        )
    return result
