"""platform_settings access for service boundary toggle."""
from __future__ import annotations

import datetime as dt
import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

SERVICE_BOUNDARY_KEY = "service_boundary_enabled"
AUDIT_ENTITY_ID = "service_boundary"


def _bool_from_json(raw: Any, default: bool = False) -> bool:
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return raw.strip().lower() in {"true", "1", "yes"}
        return _bool_from_json(parsed, default)
    if isinstance(raw, dict) and "value" in raw:
        return _bool_from_json(raw["value"], default)
    return default


async def load_service_boundary_enabled(db: AsyncSession) -> bool:
    row = (
        await db.execute(
            text(
                "SELECT value_json FROM platform_settings WHERE key = :k"
            ),
            {"k": SERVICE_BOUNDARY_KEY},
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    return _bool_from_json(row, False)


async def persist_service_boundary_enabled(
    db: AsyncSession, enabled: bool
) -> tuple[bool, dt.datetime | None]:
    before = await load_service_boundary_enabled(db)
    await db.execute(
        text(
            """
            INSERT INTO platform_settings (key, value_json, updated_at)
            VALUES (:k, CAST(:v AS jsonb), now())
            ON CONFLICT (key) DO UPDATE
            SET value_json = EXCLUDED.value_json, updated_at = now()
            """
        ),
        {"k": SERVICE_BOUNDARY_KEY, "v": json.dumps(enabled)},
    )
    updated = (
        await db.execute(
            text(
                "SELECT updated_at FROM platform_settings WHERE key = :k"
            ),
            {"k": SERVICE_BOUNDARY_KEY},
        )
    ).scalar_one_or_none()
    return before, updated