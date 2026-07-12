-- Migration 006 - duration guard (P-DUR-GUARD)
-- Apply after 005. See spec/plans/SPEC_AMENDMENTS.md section 12.

-- ---- trigger 5: NULLIF prevents COALESCE(0, 60) staying 0 ----------------
CREATE OR REPLACE FUNCTION trg_snapshot_booking_duration() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.duration_minutes IS NULL OR NEW.duration_minutes = 0 THEN
        SELECT COALESCE(NULLIF(duration_minutes, 0), 60) INTO NEW.duration_minutes
        FROM pujas WHERE id = NEW.puja_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ---- backfill before validating CHECK constraints ---------------------------
UPDATE pujas
SET duration_minutes = 60
WHERE duration_minutes IS NULL OR duration_minutes = 0;

UPDATE bookings b
SET duration_minutes = COALESCE(
    NULLIF((SELECT duration_minutes FROM pujas WHERE id = b.puja_id), 0),
    60
)
WHERE b.duration_minutes IS NULL OR b.duration_minutes = 0;

-- ---- CHECK constraints: NOT VALID first (safe on DBs with legacy bad rows) --
ALTER TABLE pujas
    ADD CONSTRAINT ck_pujas_duration_pos CHECK (duration_minutes > 0) NOT VALID;

ALTER TABLE bookings
    ADD CONSTRAINT ck_bookings_duration_pos CHECK (duration_minutes > 0) NOT VALID;

ALTER TABLE pujas VALIDATE CONSTRAINT ck_pujas_duration_pos;
ALTER TABLE bookings VALIDATE CONSTRAINT ck_bookings_duration_pos;
