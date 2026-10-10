"""Customer catalogue read helpers (Sprint 4B Wave 4 + locale i18n)."""
from __future__ import annotations

import uuid
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import PujaAddon, PujaContentItem, PujaMedia
from app.services.catalog_i18n import normalize_locale
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


async def list_customer_categories(
    db: AsyncSession, *, locale: str | None = None
) -> list[dict]:
    loc = normalize_locale(locale)
    # Telugu: te i18n, then en i18n (locale_fallback_chain) — never base columns.
    if loc == "te":
        name_expr = "COALESCE(ci.name, ci_en.name)"
        desc_expr = "COALESCE(ci.description, ci_en.description)"
        join_en = """
                LEFT JOIN puja_category_i18n ci_en
                  ON ci_en.category_id = c.id AND ci_en.locale = 'en'
        """
    else:
        name_expr = "COALESCE(ci.name, c.name)"
        desc_expr = "COALESCE(ci.description, c.description)"
        join_en = ""
    rows = (
        await db.execute(
            text(
                f"""
                SELECT c.id, c.slug, c.display_order, c.image_media_id,
                       {name_expr} AS name,
                       {desc_expr} AS description
                FROM puja_categories c
                LEFT JOIN puja_category_i18n ci
                  ON ci.category_id = c.id AND ci.locale = :locale
                {join_en}
                WHERE c.is_active
                ORDER BY c.display_order, c.id
                """
            ),
            {"locale": loc},
        )
    ).mappings().all()
    rows = [r for r in rows if r["name"] is not None]

    media_ids = [r["image_media_id"] for r in rows if r.get("image_media_id")]
    urls = await media_urls_by_ids(db, media_ids)

    return [
        {
            "id": r["id"],
            "name": r["name"],
            "slug": r["slug"] or "",
            "description": r["description"],
            "display_order": r["display_order"],
            "image_url": urls.get(r["image_media_id"]) if r.get("image_media_id") else None,
        }
        for r in rows
    ]


async def puja_price_range(db: AsyncSession, puja_id: uuid.UUID) -> tuple[Decimal, Decimal]:
    return await resolve_catalog_display_range(db, puja_id)


async def build_puja_summaries(
    db: AsyncSession, rows: list, *, locale: str | None = None
) -> list[dict]:
    if not rows:
        return []

    loc = normalize_locale(locale)
    puja_ids = [
        r["id"] if isinstance(r["id"], uuid.UUID) else uuid.UUID(str(r["id"]))
        for r in rows
    ]

    i18n_rows = (
        await db.execute(
            text(
                """
                SELECT puja_id, name, tagline
                FROM puja_i18n
                WHERE puja_id = ANY(:ids) AND locale = :loc
                """
            ),
            {"ids": [str(i) for i in puja_ids], "loc": loc},
        )
    ).mappings().all()
    i18n_map: dict[uuid.UUID, dict] = {}
    for r in i18n_rows:
        pid = r["puja_id"] if isinstance(r["puja_id"], uuid.UUID) else uuid.UUID(str(r["puja_id"]))
        i18n_map[pid] = dict(r)

    hero_ids = [r["hero_media_id"] for r in rows if r.get("hero_media_id")]
    hero_urls = await media_urls_by_ids(db, hero_ids)

    summaries: list[dict] = []
    for r in rows:
        puja_id = r["id"] if isinstance(r["id"], uuid.UUID) else uuid.UUID(str(r["id"]))
        price_from, price_to = await puja_price_range(db, puja_id)
        hero_id = r.get("hero_media_id")
        loc_row = i18n_map.get(puja_id, {})
        if loc == "te":
            name = loc_row.get("name") or ""
            tagline = loc_row.get("tagline")
        else:
            name = loc_row.get("name") or r["name"]
            tagline = loc_row.get("tagline") if loc_row.get("tagline") is not None else r.get("tagline")
        summaries.append(
            {
                "id": puja_id,
                "category_id": r["category_id"],
                "name": name,
                "slug": r.get("slug") or "",
                "tagline": tagline,
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


async def fetch_puja_detail_row(
    db: AsyncSession, puja_id: uuid.UUID, *, locale: str | None = None
) -> dict | None:
    loc = normalize_locale(locale)
    if loc == "te":
        row = (
            await db.execute(
                text(
                    """
                    SELECT p.id, p.category_id, p.slug,
                           p.duration_minutes, p.default_price, p.display_order,
                           p.hero_media_id, p.is_muhurat_bound,
                           pi.name, pi.tagline, pi.description
                    FROM pujas p
                    LEFT JOIN puja_i18n pi ON pi.puja_id = p.id AND pi.locale = 'te'
                    WHERE p.id = :id AND p.is_active
                    """
                ),
                {"id": str(puja_id)},
            )
        ).mappings().first()
    else:
        row = (
            await db.execute(
                text(
                    """
                    SELECT p.id, p.category_id, p.slug,
                           p.duration_minutes, p.default_price, p.display_order,
                           p.hero_media_id, p.is_muhurat_bound,
                           COALESCE(pi.name, p.name) AS name,
                           COALESCE(pi.tagline, p.tagline) AS tagline,
                           COALESCE(pi.description, p.description) AS description
                    FROM pujas p
                    LEFT JOIN puja_i18n pi ON pi.puja_id = p.id AND pi.locale = 'en'
                    WHERE p.id = :id AND p.is_active
                    """
                ),
                {"id": str(puja_id)},
            )
        ).mappings().first()
    if row is None:
        return None
    return dict(row)


async def fetch_puja_content_blocks(
    db: AsyncSession, puja_id: uuid.UUID, *, locale: str | None = None
) -> list[dict]:
    loc = normalize_locale(locale)
    rows = (
        await db.execute(
            select(
                PujaContentItem.kind,
                PujaContentItem.text,
                PujaContentItem.position,
            )
            .where(
                PujaContentItem.puja_id == puja_id,
                PujaContentItem.is_active.is_(True),
                PujaContentItem.locale == loc,
            )
            .order_by(PujaContentItem.kind, PujaContentItem.position)
        )
    ).all()

    grouped: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for kind, text_val, pos in rows:
        grouped[kind].append((pos, text_val))

    return [
        {
            "kind": kind,
            "items": [t for _, t in sorted(items, key=lambda x: x[0])],
        }
        for kind, items in grouped.items()
    ]


async def fetch_puja_addons(
    db: AsyncSession, puja_id: uuid.UUID, *, locale: str | None = None
) -> list[dict]:
    loc = normalize_locale(locale)
    rows = (
        await db.execute(
            select(PujaAddon)
            .where(PujaAddon.puja_id == puja_id, PujaAddon.is_active.is_(True))
            .order_by(PujaAddon.display_order, PujaAddon.id)
        )
    ).scalars().all()
    if not rows:
        return []

    addon_ids = [a.id for a in rows]
    i18n_rows = (
        await db.execute(
            text(
                """
                SELECT addon_id, name, description
                FROM puja_addon_i18n
                WHERE addon_id = ANY(:ids) AND locale = :loc
                """
            ),
            {"ids": [str(i) for i in addon_ids], "loc": loc},
        )
    ).mappings().all()
    i18n_map: dict[uuid.UUID, dict] = {}
    for r in i18n_rows:
        aid = (
            r["addon_id"]
            if isinstance(r["addon_id"], uuid.UUID)
            else uuid.UUID(str(r["addon_id"]))
        )
        i18n_map[aid] = dict(r)

    media_ids = [a.image_media_id for a in rows if a.image_media_id]
    urls = await media_urls_by_ids(db, media_ids)

    out: list[dict] = []
    for a in rows:
        loc_row = i18n_map.get(a.id, {})
        if loc == "te":
            name = loc_row.get("name") or ""
            description = loc_row.get("description")
        else:
            name = loc_row.get("name") or a.name
            description = (
                loc_row.get("description")
                if loc_row.get("description") is not None
                else a.description
            )
        out.append(
            {
                "id": a.id,
                "name": name,
                "description": description,
                "price": Decimal(str(a.price)),
                "display_order": a.display_order,
                "image_url": urls.get(a.image_media_id) if a.image_media_id else None,
            }
        )
    return out


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


async def build_puja_detail(
    db: AsyncSession, puja_id: uuid.UUID, *, locale: str | None = None
) -> dict | None:
    row = await fetch_puja_detail_row(db, puja_id, locale=locale)
    if row is None:
        return None

    pid = row["id"] if isinstance(row["id"], uuid.UUID) else uuid.UUID(str(row["id"]))
    price_from, price_to = await puja_price_range(db, pid)

    hero_id = row.get("hero_media_id")
    hero_urls = await media_urls_by_ids(db, [hero_id]) if hero_id else {}
    content = await fetch_puja_content_blocks(db, pid, locale=locale)
    addons = await fetch_puja_addons(db, pid, locale=locale)
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
