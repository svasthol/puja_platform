"""Apply migration 017 if not already applied (panchangam_daily)."""
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


def main() -> None:
    mig = Path(__file__).resolve().parents[1] / "spec" / "db" / "migration_017.sql"
    sql = mig.read_text(encoding="utf-8")
    with psycopg.connect(_sync_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_name = 'panchangam_daily'"
            )
            if cur.fetchone():
                print("migration_017: already applied (panchangam_daily exists)")
                return
        conn.execute(sql)
        conn.commit()
    print("migration_017: applied successfully")


if __name__ == "__main__":
    main()
