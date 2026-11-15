-- Migration 038 — PR2 payment reconcile scheduler (REL-005).

ALTER TABLE bookings
    ADD COLUMN IF NOT EXISTS reconcile_next_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS reconcile_attempts SMALLINT NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS ix_bookings_reconcile_next_at
    ON bookings (reconcile_next_at)
    WHERE reconcile_next_at IS NOT NULL;

UPDATE bookings
SET reconcile_next_at = now() + interval '20 minutes',
    reconcile_attempts = 0
WHERE razorpay_order_id IS NOT NULL
  AND reconcile_next_at IS NULL
  AND created_at > now() - interval '72 hours';