-- Migration 028 — TDS v3 statutory + FY latch (chains after 027).

ALTER TABLE tax_statutory_config
    ADD COLUMN IF NOT EXISTS tds_crossing_base VARCHAR(20) NOT NULL DEFAULT 'excess_slice';

ALTER TABLE tax_statutory_config DROP CONSTRAINT IF EXISTS ck_tax_statutory_tds_crossing_base;
ALTER TABLE tax_statutory_config ADD CONSTRAINT ck_tax_statutory_tds_crossing_base
    CHECK (tds_crossing_base IN ('excess_slice', 'full'));

UPDATE tax_statutory_config
SET tds_crossing_base = 'excess_slice'
WHERE tds_crossing_base IS NULL OR tds_crossing_base = 'full';

ALTER TABLE pujari_tax_year
    ADD COLUMN IF NOT EXISTS deduction_latched BOOLEAN NOT NULL DEFAULT false;

COMMENT ON COLUMN pujari_tax_year.deduction_latched IS
    'TDS v3: true after FY facilitation turnover crosses individual threshold; never cleared by reversal.';
COMMENT ON COLUMN tax_statutory_config.tds_crossing_base IS
    'TDS v3: excess_slice taxes only amount above ₹5L on crossing booking; full taxes entire amount once latched.';
