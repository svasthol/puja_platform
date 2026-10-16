"""Backfill tds_snapshot_* on bookings that have balance_collected_at but no snapshot (migration 026)."""

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
    sql = """
    UPDATE bookings b
    SET tds_snapshot_entity_type = p.entity_type,
        tds_snapshot_pan_on_file = (p.pan_hash IS NOT NULL),
        updated_at = now()
    FROM pujaris p
    WHERE b.pujari_id = p.id
      AND b.balance_collected_at IS NOT NULL
      AND b.tds_snapshot_pan_on_file IS NULL
    """
    with psycopg.connect(_sync_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'bookings'
                  AND column_name = 'tds_snapshot_pan_on_file'
                """
            )
            if cur.fetchone() is None:
                print("backfill_tds_snapshots: migration_026 not applied — skip")
                return
            cur.execute(sql)
            n = cur.rowcount
        conn.commit()
    print(f"backfill_tds_snapshots: updated {n} booking(s)")


if __name__ == "__main__":
    main()
