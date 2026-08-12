-- Migration 017 — server-cached panchangam (SPEC_AMENDMENTS §23.6, P-PANCHANGAM-API)
-- Chains after 016. Idempotent.

CREATE TABLE IF NOT EXISTS panchangam_daily (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    city                TEXT NOT NULL,
    panchang_date       DATE NOT NULL,
    locale              TEXT NOT NULL CHECK (locale IN ('te', 'en')),
    panchang_system     TEXT NOT NULL CHECK (panchang_system IN ('drik', 'vakya')),
    tithi               TEXT NOT NULL,
    nakshatram          TEXT NOT NULL,
    yoga                TEXT,
    rahu_kalam          JSONB,
    brahma_muhurtam     JSONB,
    amrita_ghadiya      JSONB,
    varjyam             JSONB,
    durmuhurtam         JSONB,
    auspicious_windows  JSONB,
    disclaimer          TEXT NOT NULL DEFAULT '',
    fetched_at          TIMESTAMPTZ NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_panchangam_daily_key
    ON panchangam_daily (city, panchang_date, locale, panchang_system);

CREATE INDEX IF NOT EXISTS ix_panchangam_daily_date_city
    ON panchangam_daily (panchang_date, city);
