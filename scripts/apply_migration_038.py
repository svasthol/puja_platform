"""Apply migration 038 (PR2 — reconcile_next_at on bookings)."""
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

_ROOT = Path(__file__).resolve().parents[1]


def _sync_url() -> str:
    url = os.environ.get(
        "DATABASE_URL", "postgresql://postgres@127.0.0.1:5433/Mana_Guruji"
    )
    return url.replace("postgresql+psycopg://", "postgresql://").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


def _already_applied(cur) -> bool:
    cur.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'bookings' AND column_name = 'reconcile_next_at'
        """
    )
    return cur.fetchone() is not None


def main() -> None:
    sql_path = _ROOT / "spec" / "db" / "migration_038.sql"
    sql = sql_path.read_text(encoding="utf-8")
    with psycopg.connect(_sync_url(), autocommit=False) as conn:
        with conn.cursor() as cur:
            if _already_applied(cur):
                print("migration_038 already applied — skip")
                return
            cur.execute(sql)
        conn.commit()
    print("migration_038 applied")


if __name__ == "__main__":
    main()