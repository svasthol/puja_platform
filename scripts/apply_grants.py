"""Apply idempotent puja_app grants (no psql required). Requires puja_app role + superuser URL."""

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
    sql_path = Path(__file__).resolve().parent / "apply_grants.sql"
    sql = sql_path.read_text(encoding="utf-8")
    try:
        with psycopg.connect(_sync_url(), autocommit=True) as conn:
            conn.execute(sql)
    except psycopg.errors.RaiseException as exc:
        if "puja_app does not exist" in str(exc):
            print(
                "apply_grants: role puja_app missing.\n"
                "  Run first: python scripts/bootstrap_puja_app_role.py",
                file=sys.stderr,
            )
            sys.exit(1)
        raise
    print("apply_grants: OK")


if __name__ == "__main__":
    main()
