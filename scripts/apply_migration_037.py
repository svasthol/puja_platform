"""Apply migration 037 (PR1 reliability — duplicate_capture + accept paid guard)."""
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
        SELECT 1 FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE t.relname = 'refunds'
          AND c.conname = 'refunds_reason_check'
          AND pg_get_constraintdef(c.oid) LIKE '%duplicate_payment%'
        """
    )
    return cur.fetchone() is not None


def main() -> None:
    ddl = (_ROOT / "spec" / "db" / "migration_037.sql").read_text(encoding="utf-8")
    with psycopg.connect(_sync_url()) as conn:
        with conn.cursor() as cur:
            if _already_applied(cur):
                print("migration_037: already applied")
                return
        conn.execute(ddl)
        conn.commit()
    print("migration_037: applied successfully")


if __name__ == "__main__":
    main()