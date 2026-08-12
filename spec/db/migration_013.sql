-- Migration 013 — advance booking reconfirmation (SPEC_AMENDMENTS §21.7, P-LAUNCH-RECONFIRM)
-- Chains after 012. Idempotent.

CREATE TABLE IF NOT EXISTS booking_reconfirmations (
    booking_id            UUID PRIMARY KEY REFERENCES bookings(id) ON DELETE CASCADE,
    ping_sent_at          TIMESTAMPTZ,
    pujari_confirmed_at   TIMESTAMPTZ,
    rm_alert_sent_at      TIMESTAMPTZ,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_booking_reconfirmations_escalation
    ON booking_reconfirmations (ping_sent_at)
    WHERE rm_alert_sent_at IS NULL AND pujari_confirmed_at IS NULL;

INSERT INTO platform_settings (key, value_json) VALUES
    ('reconfirm_lead_hours', '24'::jsonb),
    ('reconfirm_ping_hours_before_slot', '24'::jsonb),
    ('reconfirm_escalation_hours', '4'::jsonb)
ON CONFLICT (key) DO NOTHING;
