"""Status-type resolution — ALWAYS by (domain, code), never hardcoded ids.

Cached per-process after first lookup (status_types is immutable seed data).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lookups import StatusType

_cache: dict[tuple[str, str], int] = {}


async def status_id(db: AsyncSession, domain: str, code: str) -> int:
    key = (domain, code)
    if key in _cache:
        return _cache[key]
    row = (
        await db.execute(
            select(StatusType.id).where(
                StatusType.domain == domain, StatusType.code == code
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise RuntimeError(f"Seed data missing: status_types({domain}, {code})")
    _cache[key] = row
    return row
