"""Apply migration 023 if not already applied (selfie uploading status)."""
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
        SELECT pg_get_constraintdef(c.oid)
        FROM pg_constraint c
        JOIN pg_class t ON c.conrelid = t.oid
        WHERE t.relname = 'pujari_documents'
          AND c.conname = 'pujari_documents_status_check'
        """
    )
    row = cur.fetchone()
    return row is not None and "uploading" in (row[0] or "")


def main() -> None:
    mig = Path(__file__).resolve().parents[1] / "spec" / "db" / "migration_023.sql"
    sql = mig.read_text(encoding="utf-8")
    with psycopg.connect(_sync_url()) as conn:
        with conn.cursor() as cur:
            if _already_applied(cur):
                print("migration_023: already applied")
                return
        conn.execute(sql)
        conn.commit()
    print("migration_023: applied successfully")


if __name__ == "__main__":
    main()
