"""Apply TDS v3 migrations 028–032 in order (idempotent SQL — safe to re-run)."""
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

MIGRATION_NUMBERS = ("028", "029", "030", "031", "032", "033", "034")


def _sync_url() -> str:
    url = os.environ.get(
        "DATABASE_URL", "postgresql://postgres@127.0.0.1:5433/Mana_Guruji"
    )
    return url.replace("postgresql+psycopg://", "postgresql://").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


def _read_migration(number: str) -> str:
    root = Path(__file__).resolve().parents[1] / "spec" / "db"
    path = root / f"migration_{number}.sql"
    if not path.is_file():
        raise FileNotFoundError(path)
    return path.read_text(encoding="utf-8")


def main() -> None:
    with psycopg.connect(_sync_url()) as conn:
        for number in MIGRATION_NUMBERS:
            sql = _read_migration(number)
            conn.execute(sql)
            print(f"migration_{number}: applied (idempotent)")
        conn.commit()
    print("migrations 028–034: chain complete")


if __name__ == "__main__":
    main()
