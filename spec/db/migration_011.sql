-- Migration 011 — Sprint 4B Wave-0: catalogue content model (SPEC_AMENDMENTS §20)
-- Chains after 010. Idempotent — safe if columns/tables already exist.
-- Apply after 010. See spec/plans/ADMIN.md A-CAT-*.

-- ---- puja_categories extensions -------------------------------------------
ALTER TABLE puja_categories
    ADD COLUMN IF NOT EXISTS slug VARCHAR(120),
    ADD COLUMN IF NOT EXISTS description TEXT,
    ADD COLUMN IF NOT EXISTS display_order SMALLINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS image_media_id UUID;

-- is_active may already exist from migration 010
ALTER TABLE puja_categories
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

-- ---- pujas extensions -------------------------------------------------------
ALTER TABLE pujas
    ADD COLUMN IF NOT EXISTS slug VARCHAR(150),
    ADD COLUMN IF NOT EXISTS tagline VARCHAR(200),
    ADD COLUMN IF NOT EXISTS display_order SMALLINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS price_max DECIMAL(10,2),
    ADD COLUMN IF NOT EXISTS hero_media_id UUID,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_pujas_price_max_gte_default'
    ) THEN
        ALTER TABLE pujas ADD CONSTRAINT ck_pujas_price_max_gte_default
            CHECK (price_max IS NULL OR price_max >= default_price);
    END IF;
END $$;

-- ---- puja_addons extensions -------------------------------------------------
ALTER TABLE puja_addons
    ADD COLUMN IF NOT EXISTS description TEXT,
    ADD COLUMN IF NOT EXISTS display_order SMALLINT NOT NULL DEFAULT 0;

-- ---- puja_media (catalogue CDN objects) -------------------------------------
CREATE TABLE IF NOT EXISTS puja_media (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type     VARCHAR(20) NOT NULL
                      CHECK (entity_type IN ('puja', 'category', 'gallery')),
    entity_id       UUID NOT NULL,
    s3_key          VARCHAR(500) NOT NULL,
    alt_text        VARCHAR(200),
    position        SMALLINT NOT NULL DEFAULT 0,
    upload_status   VARCHAR(20) NOT NULL DEFAULT 'pending'
                      CHECK (upload_status IN ('pending', 'ready', 'failed')),
    is_active       BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    confirmed_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_puja_media_entity
    ON puja_media (entity_type, entity_id)
    WHERE is_active;

-- ---- puja_content_items (normalized bullets / FAQ) --------------------------
CREATE TABLE IF NOT EXISTS puja_content_items (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    puja_id     UUID NOT NULL REFERENCES pujas(id) ON DELETE CASCADE,
    kind        VARCHAR(20) NOT NULL
                  CHECK (kind IN ('inclusion', 'exclusion', 'insight', 'requirement', 'faq_q', 'faq_a')),
    position    SMALLINT NOT NULL DEFAULT 0,
    text        TEXT NOT NULL,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS ix_puja_content_items_puja
    ON puja_content_items (puja_id, kind, position)
    WHERE is_active;

-- ---- slug backfill (immutable after create — §20.4) -------------------------
UPDATE puja_categories
SET slug = lower(
    regexp_replace(
        regexp_replace(trim(name), '[^a-zA-Z0-9]+', '-', 'g'),
        '(^-+|-+$)', '', 'g'
    )
)
WHERE slug IS NULL OR slug = '';

UPDATE pujas p
SET slug = lower(
    regexp_replace(
        regexp_replace(trim(name), '[^a-zA-Z0-9]+', '-', 'g'),
        '(^-+|-+$)', '', 'g'
    )
) || '-' || left(replace(p.id::text, '-', ''), 8)
WHERE slug IS NULL OR slug = '';

-- display_order backfill: alphabetical within table
WITH ranked AS (
    SELECT id, row_number() OVER (ORDER BY name, id) - 1 AS ord
    FROM puja_categories
)
UPDATE puja_categories c SET display_order = ranked.ord
FROM ranked WHERE ranked.id = c.id AND c.display_order = 0;

WITH ranked AS (
    SELECT id, row_number() OVER (PARTITION BY category_id ORDER BY name, id) - 1 AS ord
    FROM pujas
)
UPDATE pujas p SET display_order = ranked.ord
FROM ranked WHERE ranked.id = p.id AND p.display_order = 0;

-- ---- unique slugs (after backfill) ------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_puja_categories_slug'
    ) THEN
        ALTER TABLE puja_categories ADD CONSTRAINT uq_puja_categories_slug UNIQUE (slug);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_pujas_slug'
    ) THEN
        ALTER TABLE pujas ADD CONSTRAINT uq_pujas_slug UNIQUE (slug);
    END IF;
END $$;

-- Optional FKs to media (nullable; set after upload confirm)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_pujas_hero_media'
    ) THEN
        ALTER TABLE pujas ADD CONSTRAINT fk_pujas_hero_media
            FOREIGN KEY (hero_media_id) REFERENCES puja_media(id);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_puja_categories_image_media'
    ) THEN
        ALTER TABLE puja_categories ADD CONSTRAINT fk_puja_categories_image_media
            FOREIGN KEY (image_media_id) REFERENCES puja_media(id);
    END IF;
END $$;
