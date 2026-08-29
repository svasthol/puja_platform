"""Apply migration 021 if not already applied (catalogue addon media + seed constraints)."""
from __future__ import annotations

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
    url = os.environ.get(
        "DATABASE_URL", "postgresql://postgres@127.0.0.1:5433/Mana_Guruji"
    )
    return url.replace("postgresql+psycopg://", "postgresql://").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


def _migration_applied(cur) -> bool:
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
        AND EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'uq_puja_content_items_puja_kind_pos'
        )
        AND EXISTS (
            SELECT 1 FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            WHERE t.relname = 'puja_media'
              AND c.conname = 'puja_media_entity_type_check'
              AND pg_get_constraintdef(c.oid) LIKE '%addon%'
        )
        """
    )
    return cur.fetchone() is not None


def main() -> None:
    mig = Path(__file__).resolve().parents[1] / "spec" / "db" / "migration_021.sql"
    sql = mig.read_text(encoding="utf-8")
    with psycopg.connect(_sync_url()) as conn:
        with conn.cursor() as cur:
            if _migration_applied(cur):
                print("migration_021: already applied")
                return
        try:
            conn.execute(sql)
            conn.commit()
        except psycopg.errors.UniqueViolation as exc:
            conn.rollback()
            print(
                "migration_021: failed — duplicate rows remain after dedupe step.\n"
                "Inspect: SELECT puja_id, name, count(*) FROM puja_addons "
                "GROUP BY 1, 2 HAVING count(*) > 1;",
                file=sys.stderr,
            )
            raise SystemExit(1) from exc
    print("migration_021: applied successfully")


if __name__ == "__main__":
    main()
