-- Migration 031 — TDS online charge lifecycle (async checkout hazard guard).

ALTER TABLE bookings ADD COLUMN IF NOT EXISTS tds_online_charge_closed_at TIMESTAMPTZ;

COMMENT ON COLUMN bookings.tds_online_charge_closed_at IS
    'When set, tds_razorpay_order_id is cleared and async TDS checkout must not reduce offline due; late pays → refund.';
