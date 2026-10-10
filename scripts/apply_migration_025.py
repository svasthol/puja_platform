"""Apply migration 025 if not already applied (Sprint 1 booking_fee)."""
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


def _column_default(cur, column: str) -> str | None:
    cur.execute(
        """
        SELECT column_default
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'bookings'
          AND column_name = %s
        """,
        (column,),
    )
    row = cur.fetchone()
    return row[0] if row else None


def _already_applied(cur) -> bool:
    cur.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'bookings'
          AND column_name = 'booking_fee'
        """
    )
    if cur.fetchone() is None:
        return False
    return _column_default(cur, "booking_fee") is not None


def _ensure_column_defaults(conn) -> list[str]:
    """Idempotent post-025 patches for test + legacy INSERT compatibility."""
    patches: list[str] = []
    with conn.cursor() as cur:
        if _column_default(cur, "booking_fee") is None:
            conn.execute("ALTER TABLE bookings ALTER COLUMN booking_fee SET DEFAULT 0")
            patches.append("booking_fee DEFAULT 0")
        if _column_default(cur, "booking_class") is None:
            conn.execute(
                "ALTER TABLE bookings ALTER COLUMN booking_class SET DEFAULT 'advance'"
            )
            patches.append("booking_class DEFAULT advance")
    if patches:
        conn.commit()
    return patches


def main() -> None:
    mig = Path(__file__).resolve().parents[1] / "spec" / "db" / "migration_025.sql"
    sql = mig.read_text(encoding="utf-8")
    with psycopg.connect(_sync_url()) as conn:
        with conn.cursor() as cur:
            applied = _already_applied(cur)
            cur.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'bookings'
                  AND column_name = 'booking_fee'
                """
            )
            column_exists = cur.fetchone() is not None
        if applied:
            patches = _ensure_column_defaults(conn)
            if patches:
                print(f"migration_025: patched {', '.join(patches)}")
            else:
                print("migration_025: already applied")
            return
        if column_exists:
            patches = _ensure_column_defaults(conn)
            msg = f"migration_025: patched {', '.join(patches)}" if patches else "migration_025: column exists"
            print(msg)
            return
        conn.execute(sql)
        conn.commit()
        patches = _ensure_column_defaults(conn)
    extra = f" (+ {', '.join(patches)})" if patches else ""
    print(f"migration_025: applied successfully{extra}")


if __name__ == "__main__":
    main()
