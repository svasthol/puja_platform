"""Soft travel-buffer check at offer accept (P-LAUNCH-BUFFER, §21.5)."""
from __future__ import annotations

import uuid

from fastapi import HTTPException, status as http
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.dispatch_launch import load_dispatch_settings_async


async def assert_accept_travel_buffer_ok(
    db: AsyncSession, *, pujari_id: uuid.UUID, booking_id: uuid.UUID
) -> None:
    """409 when another confirmed job ends within the soft buffer before this slot."""
    settings = await load_dispatch_settings_async(db)
    conflict = (
        await db.execute(
            text(
                """
                SELECT b2.id
                FROM bookings b
                JOIN bookings b2 ON b2.pujari_id = :pid AND b2.cancelled_at IS NULL AND b2.id != b.id
                JOIN status_types st ON st.id = b2.status_id
                WHERE b.id = :bid
                  AND st.domain = 'booking' AND st.code IN ('confirmed', 'in_progress')
                  AND (b2.scheduled_date + b2.scheduled_time
                       + make_interval(mins => b2.duration_minutes))
                      > (b.scheduled_date + b.scheduled_time)
                      - make_interval(mins => :buf)
                  AND (b2.scheduled_date + b2.scheduled_time
                       + make_interval(mins => b2.duration_minutes))
                      <= (b.scheduled_date + b.scheduled_time)
                LIMIT 1
                """
            ),
            {
                "pid": str(pujari_id),
                "bid": str(booking_id),
                "buf": settings.dispatch_buffer_minutes,
            },
        )
    ).scalar_one_or_none()
    if conflict is not None:
        raise HTTPException(
            http.HTTP_409_CONFLICT,
            "Travel buffer conflict — another booking ends too close to this slot.",
        )
