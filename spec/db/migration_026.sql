-- Migration 026 — TDS classification snapshot at balance collection (chains after 025).
-- §0.L-4 / L-SPRINT-2-TDS-CLASSIFICATION-CAPTURE: point-in-time entity_type + PAN-presence
-- frozen when the pujari records offline collection, so §0.S catch_up reconstructs faithfully
-- even while TDS_ACCRUAL_ENABLED=false. Fail-open: snapshot columns are nullable — collection
-- is never blocked if the write is skipped.

-- ---- bookings: TDS classification snapshot at balance collection ----------------
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS tds_snapshot_entity_type VARCHAR(20);
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS tds_snapshot_pan_on_file BOOLEAN;

ALTER TABLE bookings DROP CONSTRAINT IF EXISTS ck_bookings_tds_snapshot_entity_type;
ALTER TABLE bookings ADD CONSTRAINT ck_bookings_tds_snapshot_entity_type
    CHECK (
        tds_snapshot_entity_type IS NULL
        OR tds_snapshot_entity_type IN (
            'individual', 'huf', 'company', 'firm', 'trust', 'aop', 'other'
        )
    );

-- Snapshot must not exist before collection is recorded.
ALTER TABLE bookings DROP CONSTRAINT IF EXISTS ck_bookings_tds_snapshot_requires_collection;
ALTER TABLE bookings ADD CONSTRAINT ck_bookings_tds_snapshot_requires_collection
    CHECK (
        (tds_snapshot_entity_type IS NULL AND tds_snapshot_pan_on_file IS NULL)
        OR balance_collected_at IS NOT NULL
    );

-- Backfill existing collections from current pujari profile (best-effort; may drift if
-- PAN/entity_type changed post-collection — documented caveat in TDS_LAUNCH_STATUS.md §0.L-4).
UPDATE bookings b
SET tds_snapshot_entity_type = p.entity_type,
    tds_snapshot_pan_on_file = (p.pan_hash IS NOT NULL)
FROM pujaris p
WHERE b.pujari_id = p.id
  AND b.balance_collected_at IS NOT NULL
  AND b.tds_snapshot_pan_on_file IS NULL;

CREATE INDEX IF NOT EXISTS ix_bookings_tds_snapshot_missing
    ON bookings (balance_collected_at)
    WHERE balance_collected_at IS NOT NULL
      AND tds_snapshot_pan_on_file IS NULL;
