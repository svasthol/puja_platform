-- Migration 022: Catalogue i18n (te/en) — separate locale rows, no bilingual fields.
-- Follows panchangam locale pattern (CHECK locale IN ('te','en')).

-- ---------------------------------------------------------------------------
-- Category + puja + addon translation tables
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS puja_category_i18n (
    category_id SMALLINT NOT NULL REFERENCES puja_categories(id) ON DELETE CASCADE,
    locale      TEXT NOT NULL CHECK (locale IN ('te', 'en')),
    name        VARCHAR(150) NOT NULL,
    description TEXT,
    PRIMARY KEY (category_id, locale)
);

CREATE TABLE IF NOT EXISTS puja_i18n (
    puja_id     UUID NOT NULL REFERENCES pujas(id) ON DELETE CASCADE,
    locale      TEXT NOT NULL CHECK (locale IN ('te', 'en')),
    name        VARCHAR(150) NOT NULL,
    tagline     VARCHAR(200),
    description TEXT,
    PRIMARY KEY (puja_id, locale)
);

CREATE TABLE IF NOT EXISTS puja_addon_i18n (
    addon_id    UUID NOT NULL REFERENCES puja_addons(id) ON DELETE CASCADE,
    locale      TEXT NOT NULL CHECK (locale IN ('te', 'en')),
    name        VARCHAR(100) NOT NULL,
    description TEXT,
    PRIMARY KEY (addon_id, locale)
);

CREATE INDEX IF NOT EXISTS ix_puja_i18n_locale ON puja_i18n (locale);
CREATE INDEX IF NOT EXISTS ix_puja_category_i18n_locale ON puja_category_i18n (locale);

-- ---------------------------------------------------------------------------
-- Content items: add locale dimension (inclusion/exclusion/requirement/faq)
-- ---------------------------------------------------------------------------

ALTER TABLE puja_content_items
    ADD COLUMN IF NOT EXISTS locale TEXT NOT NULL DEFAULT 'en';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_puja_content_items_locale'
    ) THEN
        ALTER TABLE puja_content_items
            ADD CONSTRAINT chk_puja_content_items_locale
            CHECK (locale IN ('te', 'en'));
    END IF;
END $$;

-- Replace unique (puja_id, kind, position) with locale-aware key
ALTER TABLE puja_content_items
    DROP CONSTRAINT IF EXISTS uq_puja_content_items_puja_kind_pos;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_puja_content_items_puja_kind_pos_locale'
    ) THEN
        ALTER TABLE puja_content_items
            ADD CONSTRAINT uq_puja_content_items_puja_kind_pos_locale
            UNIQUE (puja_id, kind, position, locale);
    END IF;
END $$;

-- Backfill: existing rows are English canonical text
UPDATE puja_content_items SET locale = 'en' WHERE locale IS NULL OR locale = '';

-- Seed i18n from base columns where missing (English mirror)
INSERT INTO puja_category_i18n (category_id, locale, name, description)
SELECT c.id, 'en', c.name, c.description
FROM puja_categories c
WHERE NOT EXISTS (
    SELECT 1 FROM puja_category_i18n i WHERE i.category_id = c.id AND i.locale = 'en'
);

INSERT INTO puja_i18n (puja_id, locale, name, tagline, description)
SELECT p.id, 'en', p.name, p.tagline, p.description
FROM pujas p
WHERE NOT EXISTS (
    SELECT 1 FROM puja_i18n i WHERE i.puja_id = p.id AND i.locale = 'en'
);

INSERT INTO puja_addon_i18n (addon_id, locale, name, description)
SELECT a.id, 'en', a.name, a.description
FROM puja_addons a
WHERE NOT EXISTS (
    SELECT 1 FROM puja_addon_i18n i WHERE i.addon_id = a.id AND i.locale = 'en'
);
