-- Migration 039 — launch dispatch posture + admin-managed policy keys
-- Chains after 038. Idempotent.
-- Restores immediate_dispatch_on_payment when env drifted to false (rollback flag only).

INSERT INTO platform_settings (key, value_json) VALUES
    ('night_bookings_enabled', 'false'::jsonb),
    ('immediate_dispatch_on_payment', 'true'::jsonb),
    ('advance_offer_ttl_hours', '24'::jsonb),
    ('instant_offer_ttl_seconds', '120'::jsonb),
    ('rm_escalation_hours_no_accept', '24'::jsonb),
    ('rm_escalation_t24_hours', '24'::jsonb),
    ('max_live_advance_offers_per_pujari', '15'::jsonb),
    ('reconfirm_quiet_hours_start', '"22:00"'::jsonb),
    ('reconfirm_quiet_hours_end', '"08:00"'::jsonb),
    ('dispatch_buffer_minutes', '60'::jsonb),
    ('instant_lead_hours', '4'::jsonb),
    ('instant_dispatch_minutes', '30'::jsonb),
    ('advance_dispatch_start_hours', '4'::jsonb),
    ('advance_dispatch_fail_hours', '3'::jsonb),
    ('reoffer_cooldown_minutes', '45'::jsonb)
ON CONFLICT (key) DO NOTHING;

-- One-time posture: launch cut expects immediate broadcast on payment (SPEC_AMENDMENTS §21.6).
UPDATE platform_settings
SET value_json = 'true'::jsonb,
    updated_at = now()
WHERE key = 'immediate_dispatch_on_payment'
  AND value_json = 'false'::jsonb;