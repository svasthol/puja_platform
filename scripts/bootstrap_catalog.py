"""Bootstrap Hyderabad launch catalogue (6 categories, 22 pujas, te/en i18n).

Requires migration 021 + 022. Seeds English base columns + puja_*_i18n rows.

Usage:
  python scripts/apply_migration_022.py
  python scripts/bootstrap_catalog.py --force --deactivate-legacy
  python scripts/sync_active_puja_pricing.py
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))

from catalog_hyderabad_data import (
    CATEGORIES,
    PUJAS,
    SEED_CATEGORY_SLUGS,
    SEED_PUJA_SLUGS,
)
from catalog_hyderabad_te import CATEGORIES_TE, PUJAS_TE

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

try:
    import psycopg
except ImportError:
    print("psycopg not installed", file=sys.stderr)
    sys.exit(1)


def _sync_url() -> str:
    url = os.environ.get(
        "DATABASE_URL", "postgresql://postgres@127.0.0.1:5433/Mana_Guruji"
    )
    return url.replace("postgresql+psycopg://", "postgresql://").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


def _migration_021_applied(cur) -> bool:
    cur.execute(
        """
        SELECT 1
        WHERE EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'puja_addons'
              AND column_name = 'image_media_id'
        )
        AND EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'uq_puja_addons_puja_name'
        )
        """
    )
    return cur.fetchone() is not None


def _migration_022_applied(cur) -> bool:
    cur.execute(
        """
        SELECT 1
        WHERE EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'puja_i18n'
        )
        AND EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'puja_content_items'
              AND column_name = 'locale'
        )
        """
    )
    return cur.fetchone() is not None


def _require_migrations(conn) -> None:
    with conn.cursor() as cur:
        ok21 = _migration_021_applied(cur)
        ok22 = _migration_022_applied(cur)
    if not ok21:
        print("ERROR: migration_021 not applied. Run: python scripts/apply_migration_021.py", file=sys.stderr)
        sys.exit(2)
    if not ok22:
        print("ERROR: migration_022 not applied. Run: python scripts/apply_migration_022.py", file=sys.stderr)
        sys.exit(2)


def _check_bootstrap_guard(cur, *, force: bool) -> None:
    cur.execute(
        """
        SELECT slug FROM pujas
        WHERE slug IS NOT NULL AND slug NOT IN (SELECT unnest(%s::text[]))
        ORDER BY slug
        """,
        (list(SEED_PUJA_SLUGS),),
    )
    foreign = [row[0] for row in cur.fetchall()]
    if foreign and not force:
        print(
            "ERROR: catalogue has pujas outside Hyderabad seed set:\n  "
            + "\n  ".join(foreign)
            + "\nRe-run with --force to bootstrap anyway.",
            file=sys.stderr,
        )
        sys.exit(2)


def _upsert_category_i18n(cur, category_id: int, cat: dict[str, Any]) -> None:
    te = CATEGORIES_TE[cat["slug"]]
    for locale, name, description in (
        ("en", cat["name"], cat["description"]),
        ("te", te["name"], te["description"]),
    ):
        cur.execute(
            """
            INSERT INTO puja_category_i18n (category_id, locale, name, description)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (category_id, locale) DO UPDATE SET
                name = EXCLUDED.name,
                description = EXCLUDED.description
            """,
            (category_id, locale, name, description),
        )


def _upsert_categories(cur) -> dict[str, int]:
    slug_to_id: dict[str, int] = {}
    for cat in CATEGORIES:
        cur.execute(
            """
            INSERT INTO puja_categories (name, slug, description, display_order, is_active)
            VALUES (%s, %s, %s, %s, true)
            ON CONFLICT (slug) DO UPDATE SET
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                display_order = EXCLUDED.display_order,
                is_active = true
            RETURNING id
            """,
            (cat["name"], cat["slug"], cat["description"], cat["display_order"]),
        )
        row = cur.fetchone()
        if row:
            slug_to_id[cat["slug"]] = row[0]
    cur.execute(
        "SELECT id, slug FROM puja_categories WHERE slug = ANY(%s)",
        (list(SEED_CATEGORY_SLUGS),),
    )
    for row in cur.fetchall():
        slug_to_id[row[1]] = row[0]
        cat = next(c for c in CATEGORIES if c["slug"] == row[1])
        _upsert_category_i18n(cur, row[0], cat)
    missing = SEED_CATEGORY_SLUGS - slug_to_id.keys()
    if missing:
        print(f"ERROR: missing categories: {sorted(missing)}", file=sys.stderr)
        sys.exit(2)
    return slug_to_id


def _upsert_puja_i18n(cur, puja_id: uuid.UUID, puja: dict[str, Any]) -> None:
    te = PUJAS_TE[puja["slug"]]
    for locale, name, tagline, description in (
        ("en", puja["name"], puja["tagline"], puja["description"]),
        ("te", te["name"], te["tagline"], te["description"]),
    ):
        cur.execute(
            """
            INSERT INTO puja_i18n (puja_id, locale, name, tagline, description)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (puja_id, locale) DO UPDATE SET
                name = EXCLUDED.name,
                tagline = EXCLUDED.tagline,
                description = EXCLUDED.description
            """,
            (puja_id, locale, name, tagline, description),
        )


def _upsert_pujas(cur, category_ids: dict[str, int]) -> dict[str, uuid.UUID]:
    slug_to_id: dict[str, uuid.UUID] = {}
    for puja in PUJAS:
        cat_id = category_ids[puja["category_slug"]]
        cur.execute(
            """
            INSERT INTO pujas (
                category_id, name, slug, description, tagline,
                duration_minutes, default_price, price_max, display_order,
                is_active, is_muhurat_bound
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, true, %s)
            ON CONFLICT (slug) DO UPDATE SET
                category_id = EXCLUDED.category_id,
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                tagline = EXCLUDED.tagline,
                duration_minutes = EXCLUDED.duration_minutes,
                default_price = EXCLUDED.default_price,
                price_max = EXCLUDED.price_max,
                display_order = EXCLUDED.display_order,
                is_active = true,
                is_muhurat_bound = EXCLUDED.is_muhurat_bound
            RETURNING id
            """,
            (
                cat_id,
                puja["name"],
                puja["slug"],
                puja["description"],
                puja["tagline"],
                puja["duration_minutes"],
                puja["default_price"],
                puja["price_max"],
                puja["display_order"],
                puja["is_muhurat_bound"],
            ),
        )
        row = cur.fetchone()
        if row:
            pid = row[0]
            slug_to_id[puja["slug"]] = pid
            _upsert_puja_i18n(cur, pid, puja)
    cur.execute(
        "SELECT id, slug FROM pujas WHERE slug = ANY(%s)",
        (list(SEED_PUJA_SLUGS),),
    )
    for row in cur.fetchall():
        slug_to_id[row[1]] = row[0]
    missing = SEED_PUJA_SLUGS - slug_to_id.keys()
    if missing:
        print(f"ERROR: missing pujas: {sorted(missing)}", file=sys.stderr)
        sys.exit(2)
    return slug_to_id


def _replace_content(
    cur, puja_id: uuid.UUID, kind: str, texts: list[str], *, locale: str
) -> None:
    cur.execute(
        "DELETE FROM puja_content_items WHERE puja_id = %s AND kind = %s AND locale = %s",
        (puja_id, kind, locale),
    )
    for position, text in enumerate(texts):
        cur.execute(
            """
            INSERT INTO puja_content_items (
                id, puja_id, kind, position, locale, text, is_active
            )
            VALUES (%s, %s, %s, %s, %s, %s, true)
            ON CONFLICT (puja_id, kind, position, locale) DO UPDATE
            SET text = EXCLUDED.text, is_active = true
            """,
            (uuid.uuid4(), puja_id, kind, position, locale, text),
        )


def _replace_faqs(
    cur, puja_id: uuid.UUID, faqs: list[dict[str, str]], *, locale: str
) -> None:
    cur.execute(
        """
        DELETE FROM puja_content_items
        WHERE puja_id = %s AND kind IN ('faq_q', 'faq_a') AND locale = %s
        """,
        (puja_id, locale),
    )
    for position, pair in enumerate(faqs):
        for kind, text in (("faq_q", pair["q"]), ("faq_a", pair["a"])):
            cur.execute(
                """
                INSERT INTO puja_content_items (
                    id, puja_id, kind, position, locale, text, is_active
                )
                VALUES (%s, %s, %s, %s, %s, %s, true)
                ON CONFLICT (puja_id, kind, position, locale) DO UPDATE
                SET text = EXCLUDED.text, is_active = true
                """,
                (uuid.uuid4(), puja_id, kind, position, locale, text),
            )


def _upsert_addon_i18n(
    cur, addon_id: uuid.UUID, en_name: str, en_desc: str | None, te_addons: dict
) -> None:
    te = te_addons.get(en_name, {})
    for locale, name, description in (
        ("en", en_name, en_desc),
        ("te", te.get("name", en_name), te.get("description", en_desc)),
    ):
        cur.execute(
            """
            INSERT INTO puja_addon_i18n (addon_id, locale, name, description)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (addon_id, locale) DO UPDATE SET
                name = EXCLUDED.name,
                description = EXCLUDED.description
            """,
            (addon_id, locale, name, description),
        )


def _upsert_addons(cur, puja_id: uuid.UUID, puja: dict[str, Any]) -> None:
    te_addons = PUJAS_TE[puja["slug"]].get("addons", {})
    for addon in puja["addons"]:
        cur.execute(
            """
            INSERT INTO puja_addons (
                id, puja_id, name, description, price, display_order, is_active
            )
            VALUES (%s, %s, %s, %s, %s, %s, true)
            ON CONFLICT (puja_id, name) DO UPDATE SET
                description = EXCLUDED.description,
                price = EXCLUDED.price,
                display_order = EXCLUDED.display_order,
                is_active = true
            RETURNING id
            """,
            (
                uuid.uuid4(),
                puja_id,
                addon["name"],
                addon["description"],
                addon["price"],
                addon["display_order"],
            ),
        )
        row = cur.fetchone()
        if row:
            _upsert_addon_i18n(cur, row[0], addon["name"], addon.get("description"), te_addons)


def _seed_content_and_addons(cur, puja_ids: dict[str, uuid.UUID]) -> None:
    for puja in PUJAS:
        pid = puja_ids[puja["slug"]]
        te = PUJAS_TE[puja["slug"]]
        for locale, src in (("en", puja), ("te", te)):
            _replace_content(cur, pid, "inclusion", src["inclusions"], locale=locale)
            _replace_content(cur, pid, "exclusion", src["exclusions"], locale=locale)
            _replace_content(
                cur, pid, "requirement", src.get("requirements", []), locale=locale
            )
            _replace_faqs(cur, pid, src.get("faqs", []), locale=locale)
        _upsert_addons(cur, pid, puja)


def _validate_seed_data() -> None:
    assert SEED_CATEGORY_SLUGS == frozenset(c["slug"] for c in CATEGORIES)
    assert SEED_PUJA_SLUGS == frozenset(p["slug"] for p in PUJAS)
    assert set(CATEGORIES_TE.keys()) == SEED_CATEGORY_SLUGS
    assert set(PUJAS_TE.keys()) == SEED_PUJA_SLUGS
    for puja in PUJAS:
        slug = puja["slug"]
        if slug not in PUJAS_TE:
            raise ValueError(f"missing Telugu bundle for {slug}")
        if puja["duration_minutes"] <= 0:
            raise ValueError(f"{slug}: duration_minutes must be > 0")
        if puja["default_price"] <= 0:
            raise ValueError(f"{slug}: default_price must be > 0")
        if puja["price_max"] < puja["default_price"]:
            raise ValueError(f"{slug}: price_max must be >= default_price")


def _deactivate_legacy_pujas(cur) -> int:
    cur.execute(
        """
        UPDATE pujas SET is_active = false
        WHERE slug IS NOT NULL
          AND slug NOT IN (SELECT unnest(%s::text[]))
          AND is_active = true
        RETURNING slug
        """,
        (list(SEED_PUJA_SLUGS),),
    )
    return len(cur.fetchall())


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap Hyderabad launch catalogue")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--deactivate-legacy", action="store_true")
    args = parser.parse_args()

    _validate_seed_data()

    with psycopg.connect(_sync_url()) as conn:
        _require_migrations(conn)
        with conn.cursor() as cur:
            _check_bootstrap_guard(cur, force=args.force)
            category_ids = _upsert_categories(cur)
            puja_ids = _upsert_pujas(cur, category_ids)
            _seed_content_and_addons(cur, puja_ids)
            deactivated = 0
            if args.force and args.deactivate_legacy:
                deactivated = _deactivate_legacy_pujas(cur)
        conn.commit()

    msg = (
        f"bootstrap_catalog: {len(CATEGORIES)} categories, {len(PUJAS)} pujas "
        "(en+te i18n) seeded."
    )
    if args.deactivate_legacy and deactivated:
        msg += f" Deactivated {deactivated} legacy puja(s)."
    msg += " Next: python scripts/sync_active_puja_pricing.py"
    print(msg)


if __name__ == "__main__":
    main()
