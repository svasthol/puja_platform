-- Migration 025 — Sprint 1 booking_fee launch model (chains after 024).
-- Launch-lite: Razorpay = frozen booking_fee; puja collected offline by pujari.
-- TDS ledger DDL included; accrual stubbed in app until CA memo section 2.

-- ---- bookings: frozen platform fee + offline collection snapshot ----------------
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS booking_fee DECIMAL(10,2);
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS balance_collected_amount DECIMAL(10,2);

UPDATE bookings
SET booking_fee = amount_due_online
WHERE booking_fee IS NULL;

ALTER TABLE bookings ALTER COLUMN booking_fee SET DEFAULT 0;
ALTER TABLE bookings ALTER COLUMN booking_class SET DEFAULT 'advance';
ALTER TABLE bookings ALTER COLUMN booking_fee SET NOT NULL;
ALTER TABLE bookings ADD CONSTRAINT ck_bookings_booking_fee_nonneg
    CHECK (booking_fee >= 0);

ALTER TABLE bookings DROP CONSTRAINT IF EXISTS ck_bookings_payment_mode;
ALTER TABLE bookings DROP CONSTRAINT IF EXISTS ck_bookings_payment_mode_amounts;

ALTER TABLE bookings ADD CONSTRAINT ck_bookings_payment_mode
    CHECK (payment_mode IN ('full_online', 'advance_balance', 'booking_fee'));

ALTER TABLE bookings ADD CONSTRAINT ck_bookings_payment_mode_amounts
    CHECK (
        (payment_mode = 'full_online'
         AND amount_due_offline = 0
         AND amount_due_online = total_amount)
        OR
        (payment_mode = 'advance_balance'
         AND amount_due_online > 0
         AND amount_due_offline >= 0)
        OR
        (payment_mode = 'booking_fee'
         AND amount_due_online = 0
         AND amount_due_offline = total_amount
         AND booking_fee > 0)
    );

-- ---- platform settings: booking fee (new quotes only; existing rows frozen) ----
INSERT INTO platform_settings (key, value_json, updated_at)
VALUES (
    'booking_fee',
    '{"amount": 61.00, "currency": "INR", "label": "Muhurat & Slot Lock Token"}',
    now()
)
ON CONFLICT (key) DO NOTHING;

INSERT INTO platform_settings (key, value_json, updated_at)
VALUES (
    'tds_facilitation',
    '{
        "no_pan_rate_pct": 5,
        "pan_entity_rate_pct": 0.1,
        "individual_fy_threshold_inr": 500000,
        "fy_turnover_warn_inr": 1800000,
        "fy_turnover_block_inr": 2000000,
        "always_taxed_entity_types": ["firm", "trust", "company", "aop", "other"]
    }',
    now()
)
ON CONFLICT (key) DO NOTHING;

-- ---- pujaris: PAN + entity type (TDS Sprint 2; accept gate in Sprint 1) -------
ALTER TABLE pujaris ADD COLUMN IF NOT EXISTS pan_enc TEXT;
ALTER TABLE pujaris ADD COLUMN IF NOT EXISTS pan_hash VARCHAR(64);
ALTER TABLE pujaris ADD COLUMN IF NOT EXISTS entity_type VARCHAR(20);

ALTER TABLE pujaris DROP CONSTRAINT IF EXISTS ck_pujaris_entity_type;
ALTER TABLE pujaris ADD CONSTRAINT ck_pujaris_entity_type
    CHECK (
        entity_type IS NULL
        OR entity_type IN (
            'individual', 'huf', 'company', 'firm', 'trust', 'aop', 'other'
        )
    );

CREATE UNIQUE INDEX IF NOT EXISTS ux_pujaris_pan_hash
    ON pujaris (pan_hash)
    WHERE pan_hash IS NOT NULL;

-- ---- FY facilitation accumulator (FOR UPDATE at accrual; Sprint 2) ------------
CREATE TABLE IF NOT EXISTS pujari_tax_year (
    pujari_id UUID NOT NULL REFERENCES pujaris(id) ON DELETE CASCADE,
    fy_start DATE NOT NULL,
    gross_facilitation DECIMAL(14, 2) NOT NULL DEFAULT 0
        CHECK (gross_facilitation >= 0),
    tds_accrued DECIMAL(14, 2) NOT NULL DEFAULT 0
        CHECK (tds_accrued >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (pujari_id, fy_start)
);

-- ---- contra TDS facilitation ledger (append-only) -------------------------------
CREATE TABLE IF NOT EXISTS pujari_tds_facilitation_ledger (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pujari_id UUID NOT NULL REFERENCES pujaris(id) ON DELETE CASCADE,
    booking_id UUID REFERENCES bookings(id) ON DELETE SET NULL,
    entry_type VARCHAR(20) NOT NULL
        CHECK (entry_type IN ('accrual', 'reversal', 'catch_up')),
    gross_amount DECIMAL(10, 2) NOT NULL CHECK (gross_amount >= 0),
    tds_amount DECIMAL(10, 2) NOT NULL DEFAULT 0 CHECK (tds_amount >= 0),
    fy_start DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_tds_ledger_accrual_per_booking
    ON pujari_tds_facilitation_ledger (booking_id)
    WHERE entry_type = 'accrual' AND booking_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_tds_ledger_pujari_fy
    ON pujari_tds_facilitation_ledger (pujari_id, fy_start);

-- ---- pg_roles grants (guarded — mirror migration_009) -------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'puja_app') THEN
        GRANT SELECT, INSERT, UPDATE ON pujari_tax_year TO puja_app;
        GRANT SELECT, INSERT ON pujari_tds_facilitation_ledger TO puja_app;
        REVOKE UPDATE, DELETE ON pujari_tds_facilitation_ledger FROM puja_app;
    ELSE
        RAISE NOTICE 'role puja_app not found - grants skipped (dev).';
    END IF;
END $$;

COMMENT ON COLUMN bookings.booking_fee IS
    'Frozen platform fee (Razorpay amount at launch). Refund cap uses this, not amount_due_online.';
COMMENT ON COLUMN bookings.balance_collected_amount IS
    'Pujari-reported offline puja collection at confirm-balance-collected.';
COMMENT ON TABLE pujari_tds_facilitation_ledger IS
    'Contra TDS facilitation entries; accrual at confirm-balance-collected (Sprint 2).';
