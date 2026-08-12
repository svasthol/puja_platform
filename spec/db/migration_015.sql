-- Migration 015 — stuck confirmed / no-show ops alerts (P-SWEEP-CONFIRMED)
-- Chains after 014. Idempotent. Option B: alert only; admin resolves manually.

CREATE TABLE IF NOT EXISTS booking_no_show_alerts (
    booking_id         UUID PRIMARY KEY REFERENCES bookings(id) ON DELETE CASCADE,
    ops_alert_sent_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_booking_no_show_alerts_sent
    ON booking_no_show_alerts (ops_alert_sent_at);
