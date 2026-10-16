"""Slot-in-future guards for booking creation and offer accept."""
from __future__ import annotations

import datetime as dt
import uuid
import zoneinfo

from fastapi import HTTPException, status as http
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.dispatch_launch import slot_datetime

_TZ = zoneinfo.ZoneInfo(get_settings().PLATFORM_TIMEZONE)


def slot_in_past(
    scheduled_date: dt.date,
    scheduled_time: dt.time,
    *,
    now: dt.datetime | None = None,
) -> bool:
    now_utc = now or dt.datetime.now(dt.UTC)
    slot = slot_datetime(scheduled_date, scheduled_time)
    now_local = now_utc.astimezone(slot.tzinfo)
    return slot <= now_local


async def assert_slot_not_past_for_accept(
    db: AsyncSession, *, booking_id: uuid.UUID
) -> None:
    """410 when the puja slot has already started/passed."""
    row = (
        await db.execute(
            text(
                """
                SELECT b.scheduled_date, b.scheduled_time, st.code
                FROM bookings b
                JOIN status_types st ON st.id = b.status_id
                WHERE b.id = :bid
                """
            ),
            {"bid": str(booking_id)},
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "Booking not found.")
    scheduled_date, scheduled_time, status_code = row
    if status_code != "requested":
        return
    if slot_in_past(scheduled_date, scheduled_time):
        raise HTTPException(
            http.HTTP_410_GONE,
            "This slot has passed — the booking can no longer be accepted.",
        )
