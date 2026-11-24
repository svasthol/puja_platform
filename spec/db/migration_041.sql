-- Migration 041 — customer launch service boundary toggle (§21.13)
-- Chains after 040. Idempotent.

INSERT INTO platform_settings (key, value_json) VALUES
    ('service_boundary_enabled', 'false'::jsonb)
ON CONFLICT (key) DO NOTHING;