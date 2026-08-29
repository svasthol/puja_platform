"""Apply migration 022 if not already applied (catalogue i18n te/en)."""
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
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'puja_i18n'
        )
        AND EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'puja_content_items'
              AND column_name = 'locale'
        )
        AND EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'uq_puja_content_items_puja_kind_pos_locale'
        )
        """
    )
    return cur.fetchone() is not None


def main() -> None:
    mig = Path(__file__).resolve().parents[1] / "spec" / "db" / "migration_022.sql"
    sql = mig.read_text(encoding="utf-8")
    with psycopg.connect(_sync_url()) as conn:
        with conn.cursor() as cur:
            if _migration_applied(cur):
                print("migration_022: already applied")
                return
        conn.execute(sql)
        conn.commit()
    print("migration_022: applied successfully")


if __name__ == "__main__":
    main()
