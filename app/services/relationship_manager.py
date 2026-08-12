"""RM resolution + booking assignment (P-LAUNCH-RM, §21.4)."""
from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lookups import PlatformSetting
from app.models.relationship_manager import RelationshipManager
from app.schemas.relationship_manager import RelationshipManagerPublic

log = structlog.get_logger()

DEFAULT_RM_SETTING_KEY = "default_relationship_manager_id"

_STATUSES_EXPOSE_RM = frozenset(
    {"confirmed", "in_progress", "completed", "disputed"}
)


def status_exposes_rm(status_code: str) -> bool:
    return status_code in _STATUSES_EXPOSE_RM


async def get_default_rm_id(db: AsyncSession) -> uuid.UUID | None:
    row = (
        await db.execute(
            select(PlatformSetting.value_json).where(
                PlatformSetting.key == DEFAULT_RM_SETTING_KEY
            )
        )
    ).scalar_one_or_none()
    if not row:
        return None
    raw = row.get("relationship_manager_id") if isinstance(row, dict) else None
    if not raw:
        return None
    try:
        return uuid.UUID(str(raw))
    except ValueError:
        return None


async def set_default_rm_id(
    db: AsyncSession, rm_id: uuid.UUID | None
) -> None:
    if rm_id is None:
        await db.execute(
            text("DELETE FROM platform_settings WHERE key = :key"),
            {"key": DEFAULT_RM_SETTING_KEY},
        )
        return
    import json

    payload = json.dumps({"relationship_manager_id": str(rm_id)})
    await db.execute(
        text(
            """
            INSERT INTO platform_settings (key, value_json, updated_at)
            VALUES (:key, CAST(:val AS jsonb), now())
            ON CONFLICT (key) DO UPDATE
            SET value_json = EXCLUDED.value_json, updated_at = now()
            """
        ),
        {"key": DEFAULT_RM_SETTING_KEY, "val": payload},
    )


async def _active_rm_exists(db: AsyncSession, rm_id: uuid.UUID) -> bool:
    found = (
        await db.execute(
            select(RelationshipManager.id).where(
                RelationshipManager.id == rm_id,
                RelationshipManager.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    return found is not None


async def resolve_rm_id_for_booking(db: AsyncSession, booking_id: uuid.UUID) -> uuid.UUID | None:
    """Pick RM for a booking that does not yet have one assigned."""
    row = (
        await db.execute(
            text(
                """
                SELECT b.relationship_manager_id, a.city
                FROM bookings b
                JOIN addresses a ON a.id = b.address_id
                WHERE b.id = :bid
                """
            ),
            {"bid": str(booking_id)},
        )
    ).mappings().first()
    if row is None:
        return None
    if row["relationship_manager_id"] is not None:
        return uuid.UUID(str(row["relationship_manager_id"]))

    default_id = await get_default_rm_id(db)
    if default_id and await _active_rm_exists(db, default_id):
        return default_id

    city = row["city"]
    if city:
        city_rm = (
            await db.execute(
                text(
                    """
                    SELECT id FROM relationship_managers
                    WHERE is_active AND city = :city
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """
                ),
                {"city": city},
            )
        ).scalar_one_or_none()
        if city_rm is not None:
            return uuid.UUID(str(city_rm))

    fallback = (
        await db.execute(
            text(
                """
                SELECT id FROM relationship_managers
                WHERE is_active
                ORDER BY updated_at DESC
                LIMIT 1
                """
            )
        )
    ).scalar_one_or_none()
    return uuid.UUID(str(fallback)) if fallback else None


async def assign_rm_on_confirm(db: AsyncSession, booking_id: uuid.UUID) -> uuid.UUID | None:
    """Assign RM when pujari accepts (same transaction as accept_offer)."""
    rm_id = await resolve_rm_id_for_booking(db, booking_id)
    if rm_id is None:
        log.warning("no_rm_available_for_booking", booking_id=str(booking_id))
        return None
    await db.execute(
        text(
            """
            UPDATE bookings
            SET relationship_manager_id = :rm_id, updated_at = now()
            WHERE id = :bid AND relationship_manager_id IS NULL
            """
        ),
        {"rm_id": str(rm_id), "bid": str(booking_id)},
    )
    log.info("rm_assigned_on_confirm", booking_id=str(booking_id), rm_id=str(rm_id))
    return rm_id


async def fetch_default_rm_public(db: AsyncSession) -> RelationshipManagerPublic | None:
    """Active default RM for pre-booking muhurat consultation (app-config)."""
    default_id = await get_default_rm_id(db)
    if default_id is None or not await _active_rm_exists(db, default_id):
        return None
    row = (
        await db.execute(
            select(RelationshipManager.id, RelationshipManager.name, RelationshipManager.phone).where(
                RelationshipManager.id == default_id
            )
        )
    ).mappings().first()
    if row is None:
        return None
    return RelationshipManagerPublic(
        id=uuid.UUID(str(row["id"])),
        name=row["name"],
        phone=row["phone"],
    )


async def fetch_rm_public(
    db: AsyncSession, booking_id: uuid.UUID
) -> RelationshipManagerPublic | None:
    row = (
        await db.execute(
            text(
                """
                SELECT rm.id, rm.name, rm.phone
                FROM bookings b
                JOIN relationship_managers rm ON rm.id = b.relationship_manager_id
                WHERE b.id = :bid AND rm.is_active
                """
            ),
            {"bid": str(booking_id)},
        )
    ).mappings().first()
    if row is None:
        return None
    return RelationshipManagerPublic(
        id=uuid.UUID(str(row["id"])),
        name=row["name"],
        phone=row["phone"],
    )
