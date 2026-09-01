"""Apply migration 024 if not already applied (worker_heartbeats)."""
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


def _already_applied(cur) -> bool:
    cur.execute(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'worker_heartbeats'
        """
    )
    return cur.fetchone() is not None


def main() -> None:
    mig = Path(__file__).resolve().parents[1] / "spec" / "db" / "migration_024.sql"
    sql = mig.read_text(encoding="utf-8")
    with psycopg.connect(_sync_url()) as conn:
        with conn.cursor() as cur:
            if _already_applied(cur):
                print("migration_024: already applied")
                return
        conn.execute(sql)
        conn.commit()
    print("migration_024: applied successfully")


if __name__ == "__main__":
    main()
