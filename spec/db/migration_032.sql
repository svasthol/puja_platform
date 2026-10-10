-- Migration 032 — T7 accrual intent cancelled status (chains after 031).
-- Ledger refund_reference + ux_tds_ledger_reversal_ref: migration 029 only (idempotent re-run safe).

ALTER TABLE pujari_tds_accrual_intents DROP CONSTRAINT IF EXISTS pujari_tds_accrual_intents_status_check;
ALTER TABLE pujari_tds_accrual_intents ADD CONSTRAINT pujari_tds_accrual_intents_status_check
    CHECK (status IN ('pending', 'processing', 'completed', 'parked', 'failed', 'cancelled'));
