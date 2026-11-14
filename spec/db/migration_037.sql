-- Migration 037 — Production reliability PR1: duplicate_capture, duplicate_payment refund,
-- accept trigger paid_at / requested guard. Chains after 036.

ALTER TABLE refunds DROP CONSTRAINT IF EXISTS refunds_reason_check;
ALTER TABLE refunds ADD CONSTRAINT refunds_reason_check
    CHECK (reason IN (
        'customer_cancel',
        'no_pujari',
        'late_payment',
        'duplicate_payment',
        'admin_override',
        'tds_facilitation_reversal',
        'tds_late_or_double_capture',
        'tds_unexpected_capture'
    ));

ALTER TABLE payments DROP CONSTRAINT IF EXISTS payments_status_check;
ALTER TABLE payments ADD CONSTRAINT payments_status_check
    CHECK (status IN (
        'pending',
        'success',
        'failed',
        'refunded',
        'duplicate_capture'
    )) NOT VALID;
ALTER TABLE payments VALIDATE CONSTRAINT payments_status_check;

-- Trigger 3: re-accept only when paid; admin INSERT-accepted on confirmed allowed.
CREATE OR REPLACE FUNCTION trg_set_booking_pujari_on_accept() RETURNS TRIGGER AS $$
DECLARE
    v_accepted_status_id  SMALLINT;
    v_offered_status_id   SMALLINT;
    v_confirmed_status_id SMALLINT;
    v_superseded_status_id SMALLINT;
    v_current_pujari_id   UUID;
    v_cancelled_at        TIMESTAMPTZ;
    v_paid_at             TIMESTAMPTZ;
    v_booking_status_id   SMALLINT;
    v_requested_status_id SMALLINT;
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

        SELECT b.pujari_id, b.cancelled_at, b.paid_at, b.status_id
        INTO v_current_pujari_id, v_cancelled_at, v_paid_at, v_booking_status_id
        FROM bookings b WHERE b.id = NEW.booking_id FOR UPDATE;

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

            SELECT id INTO v_requested_status_id
            FROM status_types WHERE domain = 'booking' AND code = 'requested';
            IF v_requested_status_id IS NULL THEN
                RAISE EXCEPTION 'Seed data missing: status_types(domain=booking, code=requested) not found.';
            END IF;

            IF v_paid_at IS NULL THEN
                RAISE EXCEPTION 'Booking % is not acceptable (not paid).', NEW.booking_id;
            END IF;

            IF v_booking_status_id IS DISTINCT FROM v_requested_status_id THEN
                IF NOT (TG_OP = 'INSERT' AND v_booking_status_id = v_confirmed_status_id) THEN
                    RAISE EXCEPTION 'Booking % is not acceptable (status=%, paid=set).',
                        NEW.booking_id, v_booking_status_id;
                END IF;
            END IF;

            SELECT user_id INTO v_pujari_user_id FROM pujaris WHERE id = NEW.pujari_id;

            UPDATE bookings
            SET pujari_id                  = NEW.pujari_id,
                intended_pujari_id         = NEW.pujari_id,
                status_id                  = v_confirmed_status_id,
                pujari_assignment_version  = pujari_assignment_version + 1,
                updated_at                 = now()
            WHERE id = NEW.booking_id;

            INSERT INTO booking_status_history (booking_id, status_id, changed_by)
            VALUES (NEW.booking_id, v_confirmed_status_id, v_pujari_user_id);

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