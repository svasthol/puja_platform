-- =============================================================================
-- PUJA BOOKING PLATFORM — MIGRATION 003 (dual payment models)
-- Apply AFTER schema.sql + triggers.sql + seed.sql + migration 002 (see
-- spec/DATABASE.md). Canonical copy of the Migration 003 DDL block there.
--
-- Models:
--   full_online     — 100% via Razorpay (amount_due_online = total_amount)
--   advance_balance — LEAST(advance, total) online + rest offline to pujari
--
-- total_amount = full service value (puja + addons − promo), snapshotted at
-- checkout. Platform money rails touch amount_due_online ONLY.
-- =============================================================================

-- ---- platform config: advance amount (admin-tunable) ----------------------
CREATE TABLE platform_settings (
    key         VARCHAR(50) PRIMARY KEY,
    value_json  JSONB NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO platform_settings (key, value_json) VALUES
    ('advance_booking_amount', '{"amount": 250.00, "currency": "INR"}')
ON CONFLICT (key) DO NOTHING;
-- ₹250 is the LAUNCH DEFAULT only. Admin changes it via
-- PUT /v1/admin/settings/advance-booking-amount — no migration or redeploy.
-- checkout/quote and POST /v1/bookings read this row live at request time.

-- ---- bookings: payment model + amount split (snapshotted at checkout) ------
ALTER TABLE bookings ADD COLUMN payment_mode VARCHAR(20);
ALTER TABLE bookings ADD COLUMN amount_due_online  DECIMAL(10,2);
ALTER TABLE bookings ADD COLUMN amount_due_offline DECIMAL(10,2);

-- Backfill any rows created before 003 (fresh deploy after 002: zero rows)
UPDATE bookings
SET payment_mode       = 'full_online',
    amount_due_online  = total_amount,
    amount_due_offline = 0
WHERE payment_mode IS NULL;

ALTER TABLE bookings ALTER COLUMN payment_mode SET NOT NULL;
ALTER TABLE bookings ALTER COLUMN payment_mode SET DEFAULT 'full_online';
ALTER TABLE bookings ALTER COLUMN amount_due_online SET NOT NULL;
ALTER TABLE bookings ALTER COLUMN amount_due_offline SET NOT NULL;
ALTER TABLE bookings ALTER COLUMN amount_due_offline SET DEFAULT 0;

ALTER TABLE bookings ADD CONSTRAINT ck_bookings_payment_mode
    CHECK (payment_mode IN ('full_online','advance_balance'));

ALTER TABLE bookings ADD CONSTRAINT ck_bookings_amount_split
    CHECK (amount_due_online + amount_due_offline = total_amount);

-- full_online: everything through Razorpay. advance_balance: advance online,
-- balance offline (may be 0 if total <= advance — effectively full capture).
ALTER TABLE bookings ADD CONSTRAINT ck_bookings_payment_mode_amounts
    CHECK (
        (payment_mode = 'full_online'
         AND amount_due_offline = 0
         AND amount_due_online = total_amount)
        OR
        (payment_mode = 'advance_balance'
         AND amount_due_online > 0
         AND amount_due_offline >= 0)
    );

-- ---- offline balance acknowledgement (NOT a platform payment) ---------------
-- Pujari confirms they received the offline portion. Used for UX, disputes,
-- and earnings display — money never touches Razorpay or wallet_transactions.
ALTER TABLE bookings ADD COLUMN balance_collected_at TIMESTAMPTZ;
ALTER TABLE bookings ADD COLUMN balance_collected_by UUID REFERENCES users(id);
ALTER TABLE bookings ADD COLUMN balance_collection_method VARCHAR(20)
    CHECK (balance_collection_method IS NULL
           OR balance_collection_method IN ('cash','upi_direct'));

ALTER TABLE bookings ADD CONSTRAINT ck_bookings_balance_collection
    CHECK (
        (balance_collected_at IS NULL
         AND balance_collected_by IS NULL
         AND balance_collection_method IS NULL)
        OR
        (balance_collected_at IS NOT NULL
         AND balance_collected_by IS NOT NULL
         AND balance_collection_method IS NOT NULL)
    );

-- advance_balance bookings with a balance MUST record collection before complete
-- (enforced in API, not DB — offline money has no gateway to verify)
