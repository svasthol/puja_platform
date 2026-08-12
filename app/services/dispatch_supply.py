"""Dispatch supply gate — block checkout when no pujari can ever be offered (§21.2)."""
from __future__ import annotations

import datetime as dt
import uuid

from fastapi import HTTPException, status as http
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.dispatch_launch import (
    launch_eligibility_slot_sql,
    load_dispatch_settings_async,
)

# Nil UUID — pre-booking slot checks have no booking row yet.
_NO_BOOKING_ID = uuid.UUID(int=0)

NO_DISPATCH_SUPPLY_CODE = "NO_DISPATCH_SUPPLY"
NO_DISPATCH_SUPPLY_MSG = (
    "No verified pujari can perform this puja at the selected time. "
    "Try another slot or choose a different puja."
)


async def count_dispatch_eligible_for_slot(
    db: AsyncSession,
    *,
    puja_id: uuid.UUID,
    scheduled_date: dt.date,
    scheduled_time: dt.time,
    duration_minutes: int,
    exclude_booking_id: uuid.UUID | None = None,
) -> int:
    """DB-eligible pujaris for slot (Redis presence checked later at dispatch)."""
    settings = await load_dispatch_settings_async(db)
    sql = launch_eligibility_slot_sql(settings)
    rows = (
        await db.execute(
            text(sql),
            {
                "puja_id": str(puja_id),
                "scheduled_date": scheduled_date,
                "scheduled_time": scheduled_time,
                "duration_minutes": duration_minutes,
                "exclude_booking_id": str(exclude_booking_id or _NO_BOOKING_ID),
            },
        )
    ).fetchall()
    return len(rows)


async def assert_dispatch_supply(
    db: AsyncSession,
    *,
    puja_id: uuid.UUID,
    scheduled_date: dt.date,
    scheduled_time: dt.time,
    duration_minutes: int,
) -> None:
    """422 when dispatch would find zero DB candidates (e.g. missing pujari_pricing)."""
    count = await count_dispatch_eligible_for_slot(
        db,
        puja_id=puja_id,
        scheduled_date=scheduled_date,
        scheduled_time=scheduled_time,
        duration_minutes=duration_minutes,
    )
    if count == 0:
        raise HTTPException(
            http.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": NO_DISPATCH_SUPPLY_CODE,
                "message": NO_DISPATCH_SUPPLY_MSG,
            },
        )
