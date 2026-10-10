-- Migration 029 — TDS v3 online split columns + reversal idempotency (chains after 028).

ALTER TABLE bookings ADD COLUMN IF NOT EXISTS tds_collected_online DECIMAL(10, 2)
    CHECK (tds_collected_online IS NULL OR tds_collected_online >= 0);
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS tds_rate_applied DECIMAL(8, 4)
    CHECK (tds_rate_applied IS NULL OR tds_rate_applied >= 0);
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS tds_taxable_base DECIMAL(10, 2)
    CHECK (tds_taxable_base IS NULL OR tds_taxable_base >= 0);
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS tds_facilitation_fy_applied_at TIMESTAMPTZ;

COMMENT ON COLUMN bookings.tds_taxable_base IS
    'TDS v3: facilitation taxable base (excess slice or full post-latch); ledger gross_amount.';
COMMENT ON COLUMN bookings.tds_facilitation_fy_applied_at IS
    'Set when FY turnover increment + latch ran for this booking (single-writer guard).';

ALTER TABLE pujari_tds_facilitation_ledger
    ADD COLUMN IF NOT EXISTS refund_reference VARCHAR(100);

ALTER TABLE bookings DROP CONSTRAINT IF EXISTS ck_bookings_payment_mode_amounts;
ALTER TABLE bookings ADD CONSTRAINT ck_bookings_payment_mode_amounts
    CHECK (
        (payment_mode = 'full_online'
         AND amount_due_offline = 0
         AND amount_due_online = total_amount)
        OR
        (payment_mode = 'advance_balance'
         AND amount_due_online > 0
         AND amount_due_offline >= 0
         AND amount_due_online + amount_due_offline = total_amount)
        OR
        (payment_mode = 'booking_fee'
         AND booking_fee > 0
         AND amount_due_online = 0
         AND amount_due_offline >= 0
         AND amount_due_offline <= total_amount
         AND (
             tds_collected_online IS NULL
             OR amount_due_offline = total_amount - tds_collected_online
         ))
    );

DROP INDEX IF EXISTS ux_tds_ledger_reversal_per_booking;

CREATE UNIQUE INDEX IF NOT EXISTS ux_tds_ledger_reversal_ref
    ON pujari_tds_facilitation_ledger (refund_reference)
    WHERE entry_type = 'reversal' AND refund_reference IS NOT NULL;

COMMENT ON COLUMN bookings.tds_collected_online IS
    'TDS v3: portion of puja value collected on Razorpay with booking fee; pujari collects total_amount − this offline.';
COMMENT ON COLUMN bookings.tds_rate_applied IS
    'Statutory facilitation TDS rate applied at split time (decimal fraction, e.g. 0.001 = 0.1%).';

-- TDS v3 amount identity (also in migration_033 for DBs that applied 029 before this fix).
ALTER TABLE bookings DROP CONSTRAINT IF EXISTS ck_bookings_amount_split;
ALTER TABLE bookings ADD CONSTRAINT ck_bookings_amount_split
    CHECK (
        amount_due_online + amount_due_offline + COALESCE(tds_collected_online, 0) = total_amount
    );
COMMENT ON COLUMN pujari_tds_facilitation_ledger.refund_reference IS
    'T7 idempotency key for proportional reversal (unique per contra row).';
