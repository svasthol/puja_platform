-- Migration 014 — Dispatch v2 DDL (SPEC_AMENDMENTS §21.6.A–H)
-- Chains after 013. Idempotent.
-- Does NOT drop constraints, triggers, or columns from prior migrations.
-- App code (DV2-*) ships in follow-up PRs; this migration is schema + trigger 3 only.

-- ---- §21.6.A — frozen booking_class -----------------------------------------
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS booking_class VARCHAR(10);

UPDATE bookings SET booking_class = 'advance' WHERE booking_class IS NULL;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'bookings'
          AND column_name = 'booking_class'
          AND is_nullable = 'YES'
    ) THEN
        ALTER TABLE bookings ALTER COLUMN booking_class SET NOT NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_bookings_class'
    ) THEN
        ALTER TABLE bookings ADD CONSTRAINT ck_bookings_class
            CHECK (booking_class IN ('instant', 'advance'));
    END IF;
END $$;

-- ---- §21.6.E / §21.6.F — dispatch escalation markers -----------------------
ALTER TABLE booking_dispatch_state
    ADD COLUMN IF NOT EXISTS urgency_escalated_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS rm_escalated_no_accept_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS rm_escalated_t24_at TIMESTAMPTZ;

-- ---- §21.6.B — sibling-offer resolution status ------------------------------
INSERT INTO status_types (domain, code, label)
VALUES ('assignment', 'superseded', 'Superseded')
ON CONFLICT (domain, code) DO NOTHING;

-- ---- Dispatch v2 platform_settings ------------------------------------------
INSERT INTO platform_settings (key, value_json) VALUES
    ('night_bookings_enabled', 'false'::jsonb),
    ('immediate_dispatch_on_payment', 'true'::jsonb),
    ('advance_offer_ttl_hours', '24'::jsonb),
    ('instant_offer_ttl_seconds', '120'::jsonb),
    ('rm_escalation_hours_no_accept', '24'::jsonb),
    ('rm_escalation_t24_hours', '24'::jsonb),
    ('max_live_advance_offers_per_pujari', '15'::jsonb),
    ('reconfirm_quiet_hours_start', '"22:00"'::jsonb),
    ('reconfirm_quiet_hours_end', '"08:00"'::jsonb)
ON CONFLICT (key) DO NOTHING;

-- ---- §21.6.B — trigger 3 sibling supersede (v2.2) -----------------------------
CREATE OR REPLACE FUNCTION trg_set_booking_pujari_on_accept() RETURNS TRIGGER AS $$
DECLARE
    v_accepted_status_id  SMALLINT;
    v_offered_status_id   SMALLINT;
    v_confirmed_status_id SMALLINT;
    v_superseded_status_id SMALLINT;
    v_current_pujari_id   UUID;
    v_cancelled_at        TIMESTAMPTZ;
    v_pujari_user_id      UUID;
BEGIN
    SELECT id INTO v_accepted_status_id
    FROM status_types WHERE domain = 'assignment' AND code = 'accepted';

    IF v_accepted_status_id IS NULL THEN
        RAISE EXCEPTION 'Seed data missing: status_types(domain=assignment, code=accepted) not found. '
                        'The booking_assignments -> bookings.pujari_id trigger cannot function without it.';
    END IF;

    IF NEW.status_id = v_accepted_status_id THEN
        IF TG_OP = 'UPDATE' THEN
            SELECT id INTO v_offered_status_id
            FROM status_types WHERE domain = 'assignment' AND code = 'offered';
            IF v_offered_status_id IS NULL THEN
                RAISE EXCEPTION 'Seed data missing: status_types(domain=assignment, code=offered) not found.';
            END IF;
            IF OLD.status_id IS DISTINCT FROM v_offered_status_id
               AND OLD.status_id IS DISTINCT FROM v_accepted_status_id THEN
                RAISE EXCEPTION 'Assignment % was already resolved (rejected or expired) and can no longer be accepted.', NEW.id;
            END IF;
        END IF;

        IF (TG_OP = 'INSERT' OR OLD.status_id IS DISTINCT FROM v_accepted_status_id)
           AND NEW.expires_at <= now() THEN
            RAISE EXCEPTION 'This offer expired at % and can no longer be accepted.', NEW.expires_at;
        END IF;

        SELECT pujari_id, cancelled_at INTO v_current_pujari_id, v_cancelled_at
        FROM bookings WHERE id = NEW.booking_id FOR UPDATE;

        IF v_cancelled_at IS NOT NULL THEN
            RAISE EXCEPTION 'Booking % was cancelled by the customer at % and can no longer be accepted.',
                NEW.booking_id, v_cancelled_at;
        END IF;

        IF v_current_pujari_id IS NOT NULL AND v_current_pujari_id != NEW.pujari_id THEN
            RAISE EXCEPTION 'Booking % was already accepted by a different pujari. This assignment cannot also be accepted.',
                NEW.booking_id;
        END IF;

        IF v_current_pujari_id IS NULL THEN
            SELECT id INTO v_confirmed_status_id
            FROM status_types WHERE domain = 'booking' AND code = 'confirmed';
            IF v_confirmed_status_id IS NULL THEN
                RAISE EXCEPTION 'Seed data missing: status_types(domain=booking, code=confirmed) not found.';
            END IF;

            SELECT user_id INTO v_pujari_user_id FROM pujaris WHERE id = NEW.pujari_id;

            UPDATE bookings
            SET pujari_id          = NEW.pujari_id,
                intended_pujari_id = NEW.pujari_id,
                status_id          = v_confirmed_status_id,
                updated_at         = now()
            WHERE id = NEW.booking_id;

            INSERT INTO booking_status_history (booking_id, status_id, changed_by)
            VALUES (NEW.booking_id, v_confirmed_status_id, v_pujari_user_id);

            -- §21.6.B: resolve sibling live offers in the same transaction.
            SELECT id INTO v_superseded_status_id
            FROM status_types WHERE domain = 'assignment' AND code = 'superseded';
            IF v_superseded_status_id IS NULL THEN
                RAISE EXCEPTION 'Seed data missing: status_types(domain=assignment, code=superseded) not found.';
            END IF;

            UPDATE booking_assignments
            SET status_id = v_superseded_status_id,
                responded_at = now()
            WHERE booking_id = NEW.booking_id
              AND id <> NEW.id
              AND responded_at IS NULL;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
