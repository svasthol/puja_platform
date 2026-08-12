-- Migration 010 — Sprint 4B early slice: puja_categories.is_active
-- Full Wave-0 catalogue content model ships in migration 011 (SPEC_AMENDMENTS §20).
-- Apply after 009.

ALTER TABLE puja_categories
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;
