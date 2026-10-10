"""Create puja_app role (no psql required). Run as DB superuser (postgres in DATABASE_URL)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

try:
    import psycopg
except ImportError:
    print("psycopg not installed — activate .venv first", file=sys.stderr)
    sys.exit(1)


def _sync_url() -> str:
    url = os.environ.get(
        "DATABASE_URL", "postgresql://postgres@127.0.0.1:5433/Mana_Guruji"
    )
    return url.replace("postgresql+psycopg://", "postgresql://").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


def main() -> None:
    sql_path = Path(__file__).resolve().parent / "bootstrap_puja_app_role.sql"
    sql = sql_path.read_text(encoding="utf-8")
    # Bootstrap can run on any DB the superuser can connect to; grants CONNECT on Mana_Guruji.
    with psycopg.connect(_sync_url(), autocommit=True) as conn:
        conn.execute(sql)
    print("bootstrap_puja_app_role: OK (role puja_app + CONNECT on Mana_Guruji if present)")
    print("Next: python scripts/apply_grants.py")


if __name__ == "__main__":
    main()
