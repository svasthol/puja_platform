"""Customer catalogue read helpers (Sprint 4B Wave 4)."""
from __future__ import annotations

import uuid
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Puja, PujaAddon, PujaContentItem, PujaMedia
from app.models.lookups import PujaCategory
from app.services.catalog_media import public_url
from app.services.pricing_resolver import resolve_catalog_display_range


def category_entity_uuid(category_id: int) -> uuid.UUID:
    """Encode SMALLINT category PK as UUID for puja_media.entity_id (§20)."""
    return uuid.UUID(int=category_id)


async def media_urls_by_ids(
    db: AsyncSession, media_ids: list[uuid.UUID]
) -> dict[uuid.UUID, str]:
    if not media_ids:
        return {}
    rows = (
        await db.execute(
            select(PujaMedia.id, PujaMedia.s3_key).where(
                PujaMedia.id.in_(media_ids),
                PujaMedia.upload_status == "ready",
                PujaMedia.is_active.is_(True),
            )
        )
    ).all()
    out: dict[uuid.UUID, str] = {}
    for mid, s3_key in rows:
        url = public_url(s3_key)
        if url:
            out[mid] = url
    return out


async def list_customer_categories(db: AsyncSession) -> list[dict]:
    rows = (
        await db.execute(
            select(PujaCategory)
            .where(PujaCategory.is_active.is_(True))
            .order_by(PujaCategory.display_order, PujaCategory.id)
        )
    ).scalars().all()

    media_ids = [c.image_media_id for c in rows if c.image_media_id is not None]
    urls = await media_urls_by_ids(db, media_ids)

    return [
        {
            "id": c.id,
            "name": c.name,
            "slug": c.slug or "",
            "description": c.description,
            "display_order": c.display_order,
            "image_url": urls.get(c.image_media_id) if c.image_media_id else None,
        }
        for c in rows
    ]


async def puja_price_range(db: AsyncSession, puja_id: uuid.UUID) -> tuple[Decimal, Decimal]:
    return await resolve_catalog_display_range(db, puja_id)


async def build_puja_summaries(db: AsyncSession, rows: list) -> list[dict]:
    if not rows:
        return []

    hero_ids = [r["hero_media_id"] for r in rows if r.get("hero_media_id")]
    hero_urls = await media_urls_by_ids(db, hero_ids)

    summaries: list[dict] = []
    for r in rows:
        puja_id = r["id"] if isinstance(r["id"], uuid.UUID) else uuid.UUID(str(r["id"]))
        price_from, price_to = await puja_price_range(db, puja_id)
        hero_id = r.get("hero_media_id")
        summaries.append(
            {
                "id": puja_id,
                "category_id": r["category_id"],
                "name": r["name"],
                "slug": r.get("slug") or "",
                "tagline": r.get("tagline"),
                "duration_minutes": r.get("duration_minutes"),
                "default_price": Decimal(str(r["default_price"])),
                "price_from": price_from,
                "price_to": price_to,
                "display_order": r.get("display_order", 0),
                "hero_image_url": hero_urls.get(hero_id) if hero_id else None,
                "is_muhurat_bound": bool(r.get("is_muhurat_bound", False)),
            }
        )
    return summaries


async def fetch_puja_detail_row(db: AsyncSession, puja_id: uuid.UUID) -> dict | None:
    row = (
        await db.execute(
            text(
                """
                SELECT id, category_id, name, slug, tagline, description,
                       duration_minutes, default_price, display_order, hero_media_id,
                       is_muhurat_bound
                FROM pujas
                WHERE id = :id AND is_active
                """
            ),
            {"id": str(puja_id)},
        )
    ).mappings().first()
    if row is None:
        return None
    return dict(row)


async def fetch_puja_content_blocks(db: AsyncSession, puja_id: uuid.UUID) -> list[dict]:
    rows = (
        await db.execute(
            select(PujaContentItem.kind, PujaContentItem.text, PujaContentItem.position)
            .where(
                PujaContentItem.puja_id == puja_id,
                PujaContentItem.is_active.is_(True),
            )
            .order_by(PujaContentItem.kind, PujaContentItem.position)
        )
    ).all()

    grouped: dict[str, list[str]] = defaultdict(list)
    for kind, text_val, _pos in rows:
        grouped[kind].append(text_val)

    return [{"kind": kind, "items": items} for kind, items in grouped.items()]


async def fetch_puja_addons(db: AsyncSession, puja_id: uuid.UUID) -> list[dict]:
    rows = (
        await db.execute(
            select(PujaAddon)
            .where(PujaAddon.puja_id == puja_id, PujaAddon.is_active.is_(True))
            .order_by(PujaAddon.display_order, PujaAddon.id)
        )
    ).scalars().all()
    return [
        {
            "id": a.id,
            "name": a.name,
            "description": a.description,
            "price": Decimal(str(a.price)),
            "display_order": a.display_order,
        }
        for a in rows
    ]


async def fetch_puja_gallery(db: AsyncSession, puja_id: uuid.UUID) -> list[dict]:
    rows = (
        await db.execute(
            select(PujaMedia)
            .where(
                PujaMedia.entity_type == "gallery",
                PujaMedia.entity_id == puja_id,
                PujaMedia.upload_status == "ready",
                PujaMedia.is_active.is_(True),
            )
            .order_by(PujaMedia.position, PujaMedia.created_at)
        )
    ).scalars().all()

    gallery: list[dict] = []
    for m in rows:
        url = public_url(m.s3_key)
        if url:
            gallery.append(
                {"url": url, "alt_text": m.alt_text, "position": m.position}
            )
    return gallery


async def build_puja_detail(db: AsyncSession, puja_id: uuid.UUID) -> dict | None:
    row = await fetch_puja_detail_row(db, puja_id)
    if row is None:
        return None

    pid = row["id"] if isinstance(row["id"], uuid.UUID) else uuid.UUID(str(row["id"]))
    price_from, price_to = await puja_price_range(db, pid)

    hero_id = row.get("hero_media_id")
    hero_urls = await media_urls_by_ids(db, [hero_id]) if hero_id else {}
    content = await fetch_puja_content_blocks(db, pid)
    addons = await fetch_puja_addons(db, pid)
    gallery = await fetch_puja_gallery(db, pid)

    return {
        "id": pid,
        "category_id": row["category_id"],
        "name": row["name"],
        "slug": row.get("slug") or "",
        "tagline": row.get("tagline"),
        "description": row.get("description"),
        "duration_minutes": row.get("duration_minutes"),
        "default_price": Decimal(str(row["default_price"])),
        "price_from": price_from,
        "price_to": price_to,
        "display_order": row.get("display_order", 0),
        "hero_image_url": hero_urls.get(hero_id) if hero_id else None,
        "is_muhurat_bound": bool(row.get("is_muhurat_bound", False)),
        "content": content,
        "addons": addons,
        "gallery": gallery,
    }
