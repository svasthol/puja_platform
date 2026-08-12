-- Migration 016 — unified ops monitor alerts (P-MONITOR)
-- Chains after 015. Idempotent.

CREATE TABLE IF NOT EXISTS ops_monitor_alerts (
    alert_type        TEXT NOT NULL,
    subject_type      TEXT NOT NULL,
    subject_id        UUID NOT NULL,
    severity          TEXT NOT NULL,
    layer             TEXT NOT NULL,
    component         TEXT NOT NULL,
    first_seen_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    occurrence_count  INT NOT NULL DEFAULT 1,
    payload           JSONB,
    resolved_at       TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_ops_monitor_alerts_open
    ON ops_monitor_alerts (alert_type, subject_type, subject_id)
    WHERE resolved_at IS NULL;

CREATE INDEX IF NOT EXISTS ix_ops_monitor_alerts_open_type
    ON ops_monitor_alerts (alert_type, layer, component)
    WHERE resolved_at IS NULL;

CREATE INDEX IF NOT EXISTS ix_ops_monitor_alerts_subject
    ON ops_monitor_alerts (subject_type, subject_id);
