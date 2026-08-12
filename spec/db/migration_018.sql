-- Migration 018 — panchangam home-ribbon fields (SPEC_AMENDMENTS §23.6, P-PANCHANGAM-FIELDS)
-- Chains after 017. Idempotent.

ALTER TABLE panchangam_daily
    ADD COLUMN IF NOT EXISTS vaaram TEXT,
    ADD COLUMN IF NOT EXISTS yama_gandam JSONB,
    ADD COLUMN IF NOT EXISTS sunrise TEXT,
    ADD COLUMN IF NOT EXISTS sunset TEXT;
