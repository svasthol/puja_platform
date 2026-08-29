-- Migration 021 — Catalogue addon media + seed idempotency constraints (SPEC_AMENDMENTS §20.5)
-- Chains after 020. Idempotent.

-- ---- puja_addons: optional hero image --------------------------------------
ALTER TABLE puja_addons
    ADD COLUMN IF NOT EXISTS image_media_id UUID;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_puja_addons_image_media'
    ) THEN
        ALTER TABLE puja_addons ADD CONSTRAINT fk_puja_addons_image_media
            FOREIGN KEY (image_media_id) REFERENCES puja_media(id) ON DELETE SET NULL;
    END IF;
END $$;

-- ---- Deduplicate legacy rows before UNIQUE (puja_id, name) ------------------
-- Dev/test DBs may have duplicate addon names from repeated API tests.
-- Keeps lowest display_order, then id; re-points booking_addons; never deletes bookings.
WITH ranked AS (
    SELECT id,
           puja_id,
           name,
           ROW_NUMBER() OVER (
               PARTITION BY puja_id, name
               ORDER BY display_order ASC, id ASC
           ) AS rn
    FROM puja_addons
),
dup_map AS (
    SELECT loser.id AS loser_id, keeper.id AS keeper_id
    FROM ranked loser
    JOIN ranked keeper
      ON keeper.puja_id = loser.puja_id
     AND keeper.name = loser.name
     AND keeper.rn = 1
    WHERE loser.rn > 1
)
DELETE FROM booking_addons ba
USING dup_map d
WHERE ba.addon_id = d.loser_id
  AND EXISTS (
      SELECT 1
      FROM booking_addons existing
      WHERE existing.booking_id = ba.booking_id
        AND existing.addon_id = d.keeper_id
  );

WITH ranked AS (
    SELECT id,
           puja_id,
           name,
           ROW_NUMBER() OVER (
               PARTITION BY puja_id, name
               ORDER BY display_order ASC, id ASC
           ) AS rn
    FROM puja_addons
),
dup_map AS (
    SELECT loser.id AS loser_id, keeper.id AS keeper_id
    FROM ranked loser
    JOIN ranked keeper
      ON keeper.puja_id = loser.puja_id
     AND keeper.name = loser.name
     AND keeper.rn = 1
    WHERE loser.rn > 1
)
UPDATE booking_addons ba
SET addon_id = d.keeper_id
FROM dup_map d
WHERE ba.addon_id = d.loser_id;

DELETE FROM puja_addons pa
USING (
    SELECT loser.id AS loser_id
    FROM (
        SELECT id,
               puja_id,
               name,
               ROW_NUMBER() OVER (
                   PARTITION BY puja_id, name
                   ORDER BY display_order ASC, id ASC
               ) AS rn
        FROM puja_addons
    ) loser
    WHERE loser.rn > 1
) d
WHERE pa.id = d.loser_id;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_puja_addons_puja_name'
    ) THEN
        ALTER TABLE puja_addons ADD CONSTRAINT uq_puja_addons_puja_name
            UNIQUE (puja_id, name);
    END IF;
END $$;

-- ---- puja_content_items: dedupe then UNIQUE (puja_id, kind, position) -------
DELETE FROM puja_content_items a
USING puja_content_items b
WHERE a.puja_id = b.puja_id
  AND a.kind = b.kind
  AND a.position = b.position
  AND a.id > b.id;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_puja_content_items_puja_kind_pos'
    ) THEN
        ALTER TABLE puja_content_items ADD CONSTRAINT uq_puja_content_items_puja_kind_pos
            UNIQUE (puja_id, kind, position);
    END IF;
END $$;

-- ---- puja_media: allow addon entity_type ------------------------------------
ALTER TABLE puja_media DROP CONSTRAINT IF EXISTS puja_media_entity_type_check;

ALTER TABLE puja_media ADD CONSTRAINT puja_media_entity_type_check
    CHECK (entity_type IN ('puja', 'category', 'gallery', 'addon'));
