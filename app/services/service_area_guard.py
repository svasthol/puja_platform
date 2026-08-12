"""Service area deactivation guard (A-AREAS, SPEC_AMENDMENTS §21.3)."""
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lookups import ServiceArea

_TERMINAL_BOOKING_CODES = (
    "completed",
    "cancelled",
    "abandoned",
    "failed_no_pujari",
)


async def require_active_service_area(db: AsyncSession, area_id: int) -> ServiceArea:
    area = (
        await db.execute(select(ServiceArea).where(ServiceArea.id == area_id))
    ).scalar_one_or_none()
    if area is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid service_area_id.")
    if not area.is_active:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "service_area_id must reference an active service area.",
        )
    return area


async def count_pujaris_in_area(db: AsyncSession, area_id: int) -> int:
    return int(
        (
            await db.execute(
                text(
                    "SELECT count(*) FROM pujari_service_areas WHERE service_area_id = :aid"
                ),
                {"aid": area_id},
            )
        ).scalar_one()
    )


async def count_active_bookings_for_area(db: AsyncSession, area_id: int) -> int:
    """Bookings assigned to pujaris linked to this service area (non-terminal)."""
    return int(
        (
            await db.execute(
                text(
                    """
                    SELECT count(DISTINCT b.id)
                    FROM bookings b
                    JOIN pujaris pj ON pj.id = b.pujari_id
                    JOIN pujari_service_areas psa ON psa.pujari_id = pj.id
                    WHERE psa.service_area_id = :aid
                      AND b.cancelled_at IS NULL
                      AND b.status_id NOT IN (
                          SELECT id FROM status_types
                          WHERE domain = 'booking'
                            AND code = ANY(:terminal)
                      )
                    """
                ),
                {"aid": area_id, "terminal": list(_TERMINAL_BOOKING_CODES)},
            )
        ).scalar_one()
    )
