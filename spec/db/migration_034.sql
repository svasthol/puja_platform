-- Migration 034 — TDS refund reasons (chains after 033).

ALTER TABLE refunds DROP CONSTRAINT IF EXISTS refunds_reason_check;
ALTER TABLE refunds ADD CONSTRAINT refunds_reason_check
    CHECK (reason IN (
        'customer_cancel',
        'no_pujari',
        'late_payment',
        'admin_override',
        'tds_facilitation_reversal',
        'tds_late_or_double_capture',
        'tds_unexpected_capture'
    ));
