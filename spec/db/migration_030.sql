-- Migration 030 — TDS v3 recovery ledger + accept-time liability (chains after 029).

ALTER TABLE bookings ADD COLUMN IF NOT EXISTS tds_liability_inr DECIMAL(10, 2)
    CHECK (tds_liability_inr IS NULL OR tds_liability_inr >= 0);
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS tds_razorpay_order_id VARCHAR(100);

CREATE TABLE IF NOT EXISTS pujari_tds_recovery (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pujari_id UUID NOT NULL REFERENCES pujaris(id) ON DELETE CASCADE,
    booking_id UUID NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    fy_start DATE NOT NULL,
    tds_amount DECIMAL(12, 2) NOT NULL CHECK (tds_amount > 0),
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'recovered', 'void')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    recovered_at TIMESTAMPTZ,
    recovery_ref VARCHAR(100)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_tds_recovery_per_booking
    ON pujari_tds_recovery (booking_id);

CREATE INDEX IF NOT EXISTS ix_tds_recovery_pujari_pending
    ON pujari_tds_recovery (pujari_id, status)
    WHERE status = 'pending';

COMMENT ON COLUMN bookings.tds_liability_inr IS
    'Statutory TDS computed at accept (ledger + FY tds_accrued); may differ from tds_collected_online when charge fails.';
COMMENT ON TABLE pujari_tds_recovery IS
    'TDS v3: platform liability when online TDS collection at accept fails; collection gated Phase 3.';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'puja_app') THEN
        GRANT SELECT, INSERT, UPDATE ON pujari_tds_recovery TO puja_app;
    END IF;
END $$;
