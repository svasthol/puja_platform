-- =============================================================================
-- PUJA BOOKING PLATFORM — MIGRATION 002 (dispatch, refunds, geo, cancel guard)
-- Apply AFTER schema.sql + triggers.sql + seed.sql (see spec/DATABASE.md).
-- Requires PostGIS (install via PostgreSQL Stack Builder on Windows if needed).
-- =============================================================================

-- ---- extensions -----------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS postgis;

-- ---- bookings: unpaid lifecycle + committed pujari + hold linkage ----------
ALTER TABLE bookings ADD COLUMN intended_pujari_id UUID REFERENCES pujaris(id);
ALTER TABLE bookings ADD COLUMN hold_id UUID REFERENCES slot_holds(id);
ALTER TABLE bookings ADD COLUMN paid_at TIMESTAMPTZ;
ALTER TABLE bookings ADD COLUMN dispatch_mode VARCHAR(10) NOT NULL DEFAULT 'broadcast'
    CHECK (dispatch_mode IN ('direct','broadcast'));

ALTER TABLE bookings ADD CONSTRAINT ex_bookings_intended_no_overlap
    EXCLUDE USING gist (
        intended_pujari_id WITH =,
        tsrange(scheduled_date + scheduled_time,
                scheduled_date + scheduled_time + make_interval(mins => duration_minutes)) WITH &&
    ) WHERE (intended_pujari_id IS NOT NULL AND paid_at IS NOT NULL AND cancelled_at IS NULL);

-- ---- slot_holds: "any pujari" holds + conversion audit ---------------------
ALTER TABLE slot_holds ALTER COLUMN pujari_id DROP NOT NULL;
ALTER TABLE slot_holds ADD COLUMN converted_at TIMESTAMPTZ;

-- ---- refunds ---------------------------------------------------------------
CREATE TABLE refunds (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    payment_id          UUID NOT NULL REFERENCES payments(id),
    booking_id          UUID NOT NULL REFERENCES bookings(id),
    amount              DECIMAL(10,2) NOT NULL CHECK (amount > 0),
    reason              VARCHAR(30) NOT NULL
                          CHECK (reason IN ('customer_cancel','no_pujari','late_payment','admin_override')),
    status              VARCHAR(20) NOT NULL DEFAULT 'pending'
                          CHECK (status IN ('pending','processing','succeeded','failed_permanent')),
    gateway_refund_id   VARCHAR(100) UNIQUE,
    attempt_count       SMALLINT NOT NULL DEFAULT 0,
    next_attempt_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_error          TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ux_refunds_one_active_per_payment
    ON refunds (payment_id) WHERE status IN ('pending','processing');
CREATE INDEX ix_refunds_worker ON refunds (next_attempt_at)
    WHERE status IN ('pending','processing');

-- ---- payments --------------------------------------------------------------
CREATE UNIQUE INDEX ux_payments_one_success_per_booking
    ON payments (booking_id) WHERE status = 'success';

CREATE INDEX ix_bookings_status_created ON bookings (status_id, created_at);

ALTER TABLE payment_splits ADD CONSTRAINT ck_payment_splits_net_nonneg
    CHECK (net_pujari_amount >= 0);

-- ---- dispatch state --------------------------------------------------------
CREATE TABLE booking_dispatch_state (
    booking_id       UUID PRIMARY KEY REFERENCES bookings(id) ON DELETE CASCADE,
    round            SMALLINT NOT NULL DEFAULT 0,
    radius_km        DECIMAL(5,1) NOT NULL DEFAULT 3.0,
    max_rounds       SMALLINT NOT NULL DEFAULT 4,
    last_dispatched  TIMESTAMPTZ,
    exhausted_at     TIMESTAMPTZ
);

CREATE UNIQUE INDEX ux_booking_assignments_one_live
    ON booking_assignments (booking_id, pujari_id)
    WHERE responded_at IS NULL;

-- ---- geo -------------------------------------------------------------------
ALTER TABLE addresses ADD COLUMN geom GEOGRAPHY(POINT, 4326);
ALTER TABLE pujari_live_location ADD COLUMN geom GEOGRAPHY(POINT, 4326);
CREATE INDEX ix_pujari_live_location_geom ON pujari_live_location USING gist(geom);

CREATE TABLE pujari_service_areas (
    pujari_id        UUID NOT NULL REFERENCES pujaris(id) ON DELETE CASCADE,
    service_area_id  SMALLINT NOT NULL REFERENCES service_areas(id),
    PRIMARY KEY (pujari_id, service_area_id)
);

-- ---- chat ------------------------------------------------------------------
ALTER TABLE chat_messages ADD COLUMN message_type VARCHAR(10) NOT NULL DEFAULT 'text'
    CHECK (message_type IN ('text','image','system'));
ALTER TABLE chat_messages ADD COLUMN media_url VARCHAR(500);
ALTER TABLE chat_messages ADD COLUMN read_at TIMESTAMPTZ;

ALTER TABLE payouts ALTER COLUMN amount TYPE DECIMAL(12,2);

-- ---- trigger 6: cancellation state gate ------------------------------------
CREATE OR REPLACE FUNCTION trg_guard_booking_cancel() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.cancelled_at IS NOT NULL AND OLD.cancelled_at IS NULL THEN
        IF OLD.status_id IN (SELECT id FROM status_types WHERE domain = 'booking'
                             AND code IN ('in_progress','completed')) THEN
            RAISE EXCEPTION 'Booking % cannot be cancelled from its current state.', NEW.id;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER bu_bookings_cancel_guard
    BEFORE UPDATE ON bookings
    FOR EACH ROW EXECUTE FUNCTION trg_guard_booking_cancel();

INSERT INTO status_types (domain, code, label) VALUES
    ('booking', 'payment_pending',  'Payment Pending'),
    ('booking', 'abandoned',        'Abandoned'),
    ('booking', 'failed_no_pujari', 'No Pujari Found'),
    ('booking', 'disputed',         'Disputed')
ON CONFLICT DO NOTHING;
