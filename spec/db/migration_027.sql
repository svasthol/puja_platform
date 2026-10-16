-- Migration 027 — TDS accrual decouple (§0.S; chains after 026).
-- Intent queue, reversal integrity, pan_status, statutory config surface.

-- ---- pujaris: operative PAN status (R10) ------------------------------------
ALTER TABLE pujaris ADD COLUMN IF NOT EXISTS pan_status VARCHAR(20) NOT NULL DEFAULT 'unverified';

ALTER TABLE pujaris DROP CONSTRAINT IF EXISTS ck_pujaris_pan_status;
ALTER TABLE pujaris ADD CONSTRAINT ck_pujaris_pan_status
    CHECK (pan_status IN ('operative', 'inoperative', 'unverified'));

UPDATE pujaris
SET pan_status = 'operative'
WHERE pan_hash IS NOT NULL AND pan_status = 'unverified';

-- ---- statutory TDS config (R9) — puja_migrate INSERT only --------------------
CREATE TABLE IF NOT EXISTS tax_statutory_config (
    id SERIAL PRIMARY KEY,
    effective_from DATE NOT NULL UNIQUE,
    advisor_signoff_ref VARCHAR(100) NOT NULL,
    tds_no_pan_rate_pct DECIMAL(8, 4) NOT NULL,
    tds_pan_entity_rate_pct DECIMAL(8, 4) NOT NULL,
    tds_individual_fy_threshold_inr DECIMAL(14, 2) NOT NULL,
    tds_fy_turnover_warn_inr DECIMAL(14, 2) NOT NULL,
    tds_fy_turnover_block_inr DECIMAL(14, 2) NOT NULL,
    tds_always_taxed_entity_types JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO tax_statutory_config (
    effective_from,
    advisor_signoff_ref,
    tds_no_pan_rate_pct,
    tds_pan_entity_rate_pct,
    tds_individual_fy_threshold_inr,
    tds_fy_turnover_warn_inr,
    tds_fy_turnover_block_inr,
    tds_always_taxed_entity_types
)
SELECT
    '2024-10-01'::date,
    'TDS-SHADOW-SEED',
    COALESCE((value_json->>'no_pan_rate_pct')::numeric, 5),
    COALESCE((value_json->>'pan_entity_rate_pct')::numeric, 0.1),
    COALESCE((value_json->>'individual_fy_threshold_inr')::numeric, 500000),
    COALESCE((value_json->>'fy_turnover_warn_inr')::numeric, 1800000),
    COALESCE((value_json->>'fy_turnover_block_inr')::numeric, 2000000),
    COALESCE(
        value_json->'always_taxed_entity_types',
        '["firm","trust","company","aop","other"]'::jsonb
    )
FROM platform_settings
WHERE key = 'tds_facilitation'
ON CONFLICT (effective_from) DO NOTHING;

-- ---- accrual intent queue (D1/D3/R4/R13) -----------------------------------
CREATE TABLE IF NOT EXISTS pujari_tds_accrual_intents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id UUID NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    pujari_id UUID NOT NULL REFERENCES pujaris(id) ON DELETE CASCADE,
    gross_amount DECIMAL(10, 2) NOT NULL CHECK (gross_amount > 0),
    collected_at TIMESTAMPTZ NOT NULL,
    snapshot_entity_type VARCHAR(20),
    snapshot_pan_on_file BOOLEAN,
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'processing', 'completed', 'parked', 'failed')),
    park_reason VARCHAR(100),
    last_error TEXT,
    attempt_count INT NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_tds_accrual_intent_per_booking
    ON pujari_tds_accrual_intents (booking_id);

CREATE INDEX IF NOT EXISTS ix_tds_accrual_intents_pujari_collected
    ON pujari_tds_accrual_intents (pujari_id, collected_at)
    WHERE status IN ('pending', 'parked', 'processing');

-- ---- reversal integrity (R2) -------------------------------------------------
CREATE UNIQUE INDEX IF NOT EXISTS ux_tds_ledger_reversal_per_booking
    ON pujari_tds_facilitation_ledger (booking_id)
    WHERE entry_type = 'reversal' AND booking_id IS NOT NULL;

-- ---- grants (R12) ------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'puja_app') THEN
        GRANT SELECT, INSERT, UPDATE ON pujari_tds_accrual_intents TO puja_app;
        GRANT SELECT ON tax_statutory_config TO puja_app;
        REVOKE INSERT, UPDATE, DELETE ON tax_statutory_config FROM puja_app;
        REVOKE UPDATE, DELETE ON pujari_tds_facilitation_ledger FROM puja_app;
    END IF;
END $$;
