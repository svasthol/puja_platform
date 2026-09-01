-- Migration 024 — worker heartbeat table (sweep liveness; Postgres-backed, not Redis).
-- Chains after 023.

CREATE TABLE IF NOT EXISTS worker_heartbeats (
    worker_name        TEXT PRIMARY KEY,
    last_completed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_summary       JSONB
);

COMMENT ON TABLE worker_heartbeats IS
    'Last successful Celery beat task completion per worker_name (e.g. sweep).';
