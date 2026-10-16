"""Postgres-backed worker heartbeats — survives Redis outages."""
from __future__ import annotations

import json
from typing import Any

import psycopg

SWEEP_WORKER_NAME = "sweep"
SWEEP_STALE_SECONDS = 120  # 4 missed 30s ticks


def record_worker_heartbeat(
    conn: psycopg.Connection, worker_name: str, summary: dict[str, Any]
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO worker_heartbeats (worker_name, last_completed_at, last_summary)
            VALUES (%s, now(), %s::jsonb)
            ON CONFLICT (worker_name) DO UPDATE
            SET last_completed_at = EXCLUDED.last_completed_at,
                last_summary = EXCLUDED.last_summary
            """,
            (worker_name, json.dumps(summary, default=str)),
        )
    conn.commit()


def sweep_age_seconds(conn: psycopg.Connection) -> float | None:
    """Seconds since last successful sweep; None when table missing or never run."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXTRACT(EPOCH FROM (now() - last_completed_at))
            FROM worker_heartbeats
            WHERE worker_name = %s
            """,
            (SWEEP_WORKER_NAME,),
        )
        row = cur.fetchone()
    if row is None or row[0] is None:
        return None
    return float(row[0])
