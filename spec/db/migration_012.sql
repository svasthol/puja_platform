-- Migration 012 — Puja MVP launch policy (SPEC_AMENDMENTS §21)
-- Chains after 011. Idempotent — safe if columns/tables already exist.
-- Does NOT drop constraints, triggers, or columns from migrations 002–009.

-- ---- relationship_managers (RM mediator) ---------------------------------
CREATE TABLE IF NOT EXISTS relationship_managers (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(150) NOT NULL,
    phone       VARCHAR(15) NOT NULL,
    city        VARCHAR(80),
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_relationship_managers_active_city
    ON relationship_managers (city) WHERE is_active;

-- ---- bookings: per-booking RM assign ---------------------------------------
ALTER TABLE bookings
    ADD COLUMN IF NOT EXISTS relationship_manager_id UUID
        REFERENCES relationship_managers(id);

-- ---- pujas: muhurat-bound flag ---------------------------------------------
ALTER TABLE pujas
    ADD COLUMN IF NOT EXISTS is_muhurat_bound BOOLEAN NOT NULL DEFAULT FALSE;

-- ---- dispatch: deferred broadcast windows ----------------------------------
ALTER TABLE booking_dispatch_state
    ADD COLUMN IF NOT EXISTS dispatch_starts_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS dispatch_deadline TIMESTAMPTZ;

-- ---- addresses: mandatory service area (display label at launch) -------------
ALTER TABLE addresses
    ADD COLUMN IF NOT EXISTS service_area_id SMALLINT REFERENCES service_areas(id);

-- Backfill legacy rows before NOT NULL (E1 pattern: nullable → backfill → NOT NULL)
INSERT INTO service_areas (city, zone_name, is_active)
VALUES ('Hyderabad', 'Legacy (migration)', TRUE)
ON CONFLICT (city, zone_name) DO NOTHING;

UPDATE addresses
SET service_area_id = (
    SELECT id FROM service_areas
    WHERE city = 'Hyderabad' AND zone_name = 'Legacy (migration)'
    LIMIT 1
)
WHERE service_area_id IS NULL;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'addresses'
          AND column_name = 'service_area_id'
          AND is_nullable = 'YES'
    ) THEN
        ALTER TABLE addresses ALTER COLUMN service_area_id SET NOT NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_addresses_service_area
    ON addresses (service_area_id);

-- ---- platform_settings: launch dispatch + RM defaults ----------------------
INSERT INTO platform_settings (key, value_json) VALUES
    ('dispatch_buffer_minutes', '60'::jsonb),
    ('instant_lead_hours', '4'::jsonb),
    ('instant_dispatch_minutes', '30'::jsonb),
    ('advance_dispatch_start_hours', '4'::jsonb),
    ('advance_dispatch_fail_hours', '3'::jsonb),
    ('reoffer_cooldown_minutes', '45'::jsonb)
ON CONFLICT (key) DO NOTHING;
