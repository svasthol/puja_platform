-- Migration 019 — panchangam angā end times for home ribbon (§23.6)
-- Chains after 018. Idempotent.

ALTER TABLE panchangam_daily
    ADD COLUMN IF NOT EXISTS tithi_end TEXT,
    ADD COLUMN IF NOT EXISTS nakshatra_end TEXT,
    ADD COLUMN IF NOT EXISTS yoga_end TEXT;
