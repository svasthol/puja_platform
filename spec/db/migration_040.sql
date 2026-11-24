-- Migration 040 — urgency escalation dispatch (§21.6.E expand, B11 morning wake)
-- Chains after 039. Idempotent.

ALTER TABLE booking_dispatch_state
    ADD COLUMN IF NOT EXISTS escalated_holders_shortened_at TIMESTAMPTZ NULL;

INSERT INTO platform_settings (key, value_json) VALUES
    ('urgency_escalation_lead_hours', '4'::jsonb),
    ('escalated_offer_ttl_seconds', '900'::jsonb),
    ('rebroadcast_on_urgency_flip', 'true'::jsonb)
ON CONFLICT (key) DO NOTHING;