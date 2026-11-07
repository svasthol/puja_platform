-- Migration 035 — Customer trust card (Slice A): public display name + assignment version.
-- Chains after 034. No profile photo columns (Slice B).
-- Accept-trigger bump is re-applied from spec/db/triggers.sql by scripts/apply_migration_035.py.

ALTER TABLE pujaris
    ADD COLUMN IF NOT EXISTS public_name VARCHAR(100),
    ADD COLUMN IF NOT EXISTS public_name_pending VARCHAR(100),
    ADD COLUMN IF NOT EXISTS public_name_approved_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS public_name_visible BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE bookings
    ADD COLUMN IF NOT EXISTS pujari_assignment_version INT NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS public_name_audit (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pujari_id     UUID NOT NULL REFERENCES pujaris(id) ON DELETE CASCADE,
    action        VARCHAR(30) NOT NULL CHECK (action IN ('proposed', 'approved', 'rejected')),
    name_value    VARCHAR(100),
    admin_user_id UUID REFERENCES users(id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_public_name_audit_pujari
    ON public_name_audit (pujari_id, created_at DESC);

INSERT INTO platform_settings (key, value_json) VALUES
    ('feature_trust_card_enabled', '{"enabled": false}')
ON CONFLICT (key) DO NOTHING;
