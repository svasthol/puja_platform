"""Auto-provision verified pujaris for dispatch supply (§21.2 city membership + availability).

Idempotent: safe to call on every transition to ``verified`` or when a new active puja is
created. Mirrors dev backfill in ``scripts/sync_partner_dispatch_readiness.py`` and
``scripts/sync_active_puja_pricing.py``.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger()

# Launch city membership — citywide broadcast, not per-customer area (LAUNCH_POLICY.md).
DEFAULT_LAUNCH_CITY = "Hyderabad"
DEFAULT_LAUNCH_ZONE = "Default"
DEFAULT_AVAIL_START = "06:00"
DEFAULT_AVAIL_END = "23:59"


@dataclass(frozen=True)
class PartnerReadinessResult:
    service_areas_linked: int
    availability_inserted: int
    pricing_inserted: int


@dataclass(frozen=True)
class PujaPricingSyncResult:
    pricing_inserted: int


async def _ensure_default_launch_service_area(db: AsyncSession) -> None:
    await db.execute(
        text(
            """
            INSERT INTO service_areas (city, zone_name, is_active)
            VALUES (:city, :zone, true)
            ON CONFLICT (city, zone_name) DO NOTHING
            """
        ),
        {"city": DEFAULT_LAUNCH_CITY, "zone": DEFAULT_LAUNCH_ZONE},
    )


async def ensure_partner_dispatch_readiness(
    db: AsyncSession,
    *,
    pujari_id: uuid.UUID,
) -> PartnerReadinessResult:
    """Link verified pujari to active service areas, default weekly hours, and catalogue pricing."""
    await _ensure_default_launch_service_area(db)

    area_rows = (
        await db.execute(
            text(
                """
                INSERT INTO pujari_service_areas (pujari_id, service_area_id)
                SELECT :pid, sa.id
                FROM service_areas sa
                WHERE sa.is_active = true
                  AND NOT EXISTS (
                    SELECT 1 FROM pujari_service_areas psa
                    WHERE psa.pujari_id = :pid AND psa.service_area_id = sa.id
                  )
                RETURNING service_area_id
                """
            ),
            {"pid": str(pujari_id)},
        )
    ).fetchall()

    avail_rows = (
        await db.execute(
            text(
                """
                INSERT INTO pujari_availability (id, pujari_id, day_of_week, start_time, end_time)
                SELECT gen_random_uuid(), :pid, dow.d, CAST(:start_t AS time), CAST(:end_t AS time)
                FROM generate_series(0, 6) AS dow(d)
                WHERE NOT EXISTS (
                  SELECT 1 FROM pujari_availability pa
                  WHERE pa.pujari_id = :pid AND pa.day_of_week = dow.d
                )
                RETURNING day_of_week
                """
            ),
            {
                "pid": str(pujari_id),
                "start_t": DEFAULT_AVAIL_START,
                "end_t": DEFAULT_AVAIL_END,
            },
        )
    ).fetchall()

    pricing_rows = (
        await db.execute(
            text(
                """
                INSERT INTO pujari_pricing (id, pujari_id, puja_id, base_price)
                SELECT gen_random_uuid(), :pid, p.id, p.default_price
                FROM pujas p
                WHERE p.is_active = true
                  AND NOT EXISTS (
                    SELECT 1 FROM pujari_pricing pp
                    WHERE pp.pujari_id = :pid AND pp.puja_id = p.id
                  )
                RETURNING puja_id
                """
            ),
            {"pid": str(pujari_id)},
        )
    ).fetchall()

    result = PartnerReadinessResult(
        service_areas_linked=len(area_rows),
        availability_inserted=len(avail_rows),
        pricing_inserted=len(pricing_rows),
    )
    if any((result.service_areas_linked, result.availability_inserted, result.pricing_inserted)):
        log.info(
            "partner_dispatch_readiness_applied",
            pujari_id=str(pujari_id),
            service_areas_linked=result.service_areas_linked,
            availability_inserted=result.availability_inserted,
            pricing_inserted=result.pricing_inserted,
        )
    return result


async def ensure_puja_pricing_for_verified_pujaris(
    db: AsyncSession,
    *,
    puja_id: uuid.UUID,
) -> PujaPricingSyncResult:
    """Backfill ``pujari_pricing`` for one active puja across all verified pujaris."""
    rows = (
        await db.execute(
            text(
                """
                INSERT INTO pujari_pricing (id, pujari_id, puja_id, base_price)
                SELECT gen_random_uuid(), pj.id, p.id, p.default_price
                FROM pujas p
                CROSS JOIN pujaris pj
                WHERE p.id = :puja_id
                  AND p.is_active = true
                  AND pj.verification_status = 'verified'
                  AND NOT EXISTS (
                    SELECT 1 FROM pujari_pricing pp
                    WHERE pp.pujari_id = pj.id AND pp.puja_id = p.id
                  )
                RETURNING pujari_id
                """
            ),
            {"puja_id": str(puja_id)},
        )
    ).fetchall()
    result = PujaPricingSyncResult(pricing_inserted=len(rows))
    if result.pricing_inserted:
        log.info(
            "puja_pricing_synced_for_verified_pujaris",
            puja_id=str(puja_id),
            pricing_inserted=result.pricing_inserted,
        )
    return result
