"""Apply migration 035 (trust card Slice A) if not already applied."""
from __future__ import annotations

import os
import re
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
        WHERE table_schema = 'public'
          AND table_name = 'bookings'
          AND column_name = 'pujari_assignment_version'
        """
    )
    return cur.fetchone() is not None


def _accept_trigger_sql() -> str:
    text = (_ROOT / "spec" / "db" / "triggers.sql").read_text(encoding="utf-8")
    match = re.search(
        r"(CREATE OR REPLACE FUNCTION trg_set_booking_pujari_on_accept\(\).*?\$\$ LANGUAGE plpgsql;)",
        text,
        re.DOTALL,
    )
    if not match:
        raise RuntimeError("trg_set_booking_pujari_on_accept not found in triggers.sql")
    return match.group(1)


def main() -> None:
    ddl = (_ROOT / "spec" / "db" / "migration_035.sql").read_text(encoding="utf-8")
    trigger_sql = _accept_trigger_sql()
    with psycopg.connect(_sync_url()) as conn:
        with conn.cursor() as cur:
            if _already_applied(cur):
                print("migration_035: already applied")
                return
        conn.execute(ddl)
        conn.execute(trigger_sql)
        conn.commit()
    print("migration_035: applied successfully")


if __name__ == "__main__":
    main()
