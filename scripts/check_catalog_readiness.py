"""Catalogue launch readiness — active rows must be customer-visible."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

try:
    import psycopg
except ImportError:
    print("psycopg not installed", file=sys.stderr)
    sys.exit(1)


def _sync_url() -> str:
    url = os.environ.get("DATABASE_URL", "postgresql://postgres@127.0.0.1:5432/Mana_Guruji")
    return url.replace("postgresql+psycopg://", "postgresql://").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Catalogue launch readiness")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 if any active puja/category fails customer visibility rules",
    )
    args = parser.parse_args()
    blockers: list[str] = []

    with psycopg.connect(_sync_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.id::text, p.name
                FROM pujas p
                WHERE p.is_active
                  AND (
                    p.slug IS NULL OR trim(p.slug) = ''
                    OR NOT EXISTS (
                        SELECT 1 FROM puja_i18n i
                        WHERE i.puja_id = p.id AND i.locale = 'te' AND trim(i.name) <> ''
                    )
                    OR NOT EXISTS (
                        SELECT 1 FROM pujari_pricing pp
                        JOIN pujaris pj ON pj.id = pp.pujari_id
                        WHERE pp.puja_id = p.id AND pj.verification_status = 'verified'
                    )
                  )
                LIMIT 20
                """
            )
            bad_pujas = cur.fetchall()
            if bad_pujas:
                blockers.append(
                    f"active pujas failing customer visibility: {len(bad_pujas)} (showing up to 20)"
                )
                for pid, name in bad_pujas:
                    print(f"  puja {pid} name={name!r}")

            cur.execute(
                """
                SELECT c.id, c.name
                FROM puja_categories c
                WHERE c.is_active
                  AND NOT EXISTS (
                    SELECT 1 FROM puja_category_i18n ci
                    WHERE ci.category_id = c.id AND ci.locale = 'te' AND trim(ci.name) <> ''
                  )
                LIMIT 20
                """
            )
            bad_cats = cur.fetchall()
            if bad_cats:
                blockers.append(
                    f"active categories missing te puja_category_i18n: {len(bad_cats)}"
                )
                for cid, name in bad_cats:
                    print(f"  category {cid} name={name!r}")

            if not args.strict:
                cur.execute(
                    """
                    SELECT p.id::text, p.name FROM pujas p
                    WHERE p.is_active
                      AND (p.name ILIKE 'test %' OR p.name ILIKE '%test puja%')
                    LIMIT 10
                    """
                )
                for row in cur.fetchall():
                    print(f"WARN test-like active puja: {row[0]} {row[1]!r}")

    if blockers:
        print("=== CATALOG READINESS: FAIL ===")
        for b in blockers:
            print(f"  - {b}")
        if args.strict:
            sys.exit(1)
    else:
        print("=== CATALOG READINESS: OK ===")
        if args.strict:
            sys.exit(0)


if __name__ == "__main__":
    main()
