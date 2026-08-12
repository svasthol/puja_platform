-- =============================================================================
-- TRIGGER 1 â€” payment_splits.net_pujari_amount (computed, never written by app code)
-- v2: refuses a negative payout â€” a fee/GST misconfiguration must fail loudly,
-- never silently write a negative amount a payout worker would then act on.
-- =============================================================================
CREATE OR REPLACE FUNCTION trg_compute_net_pujari_amount() RETURNS TRIGGER AS $$
DECLARE
    v_amount DECIMAL(10,2);
BEGIN
    SELECT amount INTO v_amount FROM payments WHERE id = NEW.payment_id;
    NEW.net_pujari_amount := v_amount - NEW.platform_fee - NEW.gst_amount;
    IF NEW.net_pujari_amount < 0 THEN
        RAISE EXCEPTION 'payment_splits: platform_fee % + gst_amount % exceed payment amount % â€” negative pujari payout refused.',
            NEW.platform_fee, NEW.gst_amount, v_amount;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER bi_payment_splits_net_amount
    BEFORE INSERT OR UPDATE ON payment_splits
    FOR EACH ROW EXECUTE FUNCTION trg_compute_net_pujari_amount();

-- =============================================================================
-- TRIGGER 2 â€” pujaris.rating_avg / rating_count (recomputed from reviews)
-- =============================================================================
CREATE OR REPLACE FUNCTION trg_recompute_pujari_rating() RETURNS TRIGGER AS $$
DECLARE
    v_pujari_id UUID := COALESCE(NEW.pujari_id, OLD.pujari_id);
BEGIN
    UPDATE pujaris
    SET rating_avg   = COALESCE((SELECT ROUND(AVG(rating), 2) FROM reviews WHERE pujari_id = v_pujari_id), 0),
        rating_count = (SELECT COUNT(*) FROM reviews WHERE pujari_id = v_pujari_id),
        updated_at   = now()
    WHERE id = v_pujari_id;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER aiud_reviews_rating_sync
    AFTER INSERT OR UPDATE OR DELETE ON reviews
    FOR EACH ROW EXECUTE FUNCTION trg_recompute_pujari_rating();

-- =============================================================================
-- TRIGGER 3 — accept resolution (v2.2 — migration 014 sibling supersede).
-- On the first valid accept, atomically and in the accepting transaction:
--   * writes bookings.pujari_id AND bookings.intended_pujari_id
--   * flips the booking to (booking, confirmed)
--   * inserts the booking_status_history row (changed_by = pujari's user)
--   * supersedes every other live offer for that booking (§21.6.B)
-- Writing intended_pujari_id is NOT cosmetic: it puts every accepted booking
-- under ex_bookings_intended_no_overlap (paid_at is always set before offers
-- exist), which closes the cross-mode overlap hole — a pujari who is the
-- intended pujari of a PAID direct booking cannot accept an overlapping
-- broadcast booking; the exclusion constraint raises here, at the DB layer,
-- even if the dispatch eligibility query missed it.
-- Guards (in order): offer must be live 'offered' (no resurrecting rejected /
-- expired rows), offer unexpired by time (fresh accepts only — an idempotent
-- re-fire of an already-accepted row is NOT time-checked, so a network retry
-- of a successful accept arriving after expires_at cannot spuriously fail),
-- booking not cancelled, booking not taken by another pujari. Idempotent: a
-- re-fired accept by the SAME pujari passes the guards but writes nothing
-- twice. Fails LOUDLY if any expected status_types seed row is missing.
-- =============================================================================
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
        -- Guard 0 (v2): only a live 'offered' assignment can transition to
        -- accepted. A row already rejected or expired is terminal â€” a pujari
        -- cannot change their mind after rejecting, and a sweep-expired offer
        -- cannot be resurrected. (An already-accepted row falls through so an
        -- idempotent re-fire by the same pujari is harmless; Guard 3 rejects
        -- a different pujari.) INSERTs skip this guard: direct insert of an
        -- accepted row is the admin manual-reassign path (which MUST clear
        -- pujari_id + intended_pujari_id first â€” Guard 3 rejects the insert
        -- while the old pujari is still set; see API_CONTRACTS.md), still
        -- subject to Guards 1â€“3 and both exclusion constraints.
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

        -- Guard 1: an expired offer can no longer be accepted, even if the sweep
        -- worker hasn't flipped its status yet. Scoped to FRESH accepts only:
        -- an idempotent re-fire of an already-accepted row (OLD.status_id =
        -- accepted) skips this check â€” the offer was won before it expired,
        -- and a client retry arriving late must not see a spurious failure.
        IF (TG_OP = 'INSERT' OR OLD.status_id IS DISTINCT FROM v_accepted_status_id)
           AND NEW.expires_at <= now() THEN
            RAISE EXCEPTION 'This offer expired at % and can no longer be accepted.', NEW.expires_at;
        END IF;

        -- Lock the booking row so two near-simultaneous accepts (two pujaris both tapping
        -- "accept" on the same broadcast offer) are serialized, not raced. The second
        -- transaction blocks here until the first commits, then sees the row is taken.
        SELECT pujari_id, cancelled_at INTO v_current_pujari_id, v_cancelled_at
        FROM bookings WHERE id = NEW.booking_id FOR UPDATE;

        -- Guard 2: the customer may have cancelled while offers were pending.
        IF v_cancelled_at IS NOT NULL THEN
            RAISE EXCEPTION 'Booking % was cancelled by the customer at % and can no longer be accepted.',
                NEW.booking_id, v_cancelled_at;
        END IF;

        IF v_current_pujari_id IS NOT NULL AND v_current_pujari_id != NEW.pujari_id THEN
            RAISE EXCEPTION 'Booking % was already accepted by a different pujari. This assignment cannot also be accepted.',
                NEW.booking_id;
        END IF;

        -- First accept only: idempotent re-fire by the winner writes nothing twice
        -- (no duplicate history row, no redundant booking UPDATE).
        IF v_current_pujari_id IS NULL THEN
            SELECT id INTO v_confirmed_status_id
            FROM status_types WHERE domain = 'booking' AND code = 'confirmed';
            IF v_confirmed_status_id IS NULL THEN
                RAISE EXCEPTION 'Seed data missing: status_types(domain=booking, code=confirmed) not found.';
            END IF;

            SELECT user_id INTO v_pujari_user_id FROM pujaris WHERE id = NEW.pujari_id;

            -- This UPDATE is checked by BOTH exclusion constraints:
            --   * ex_bookings_pujari_no_overlap (pujari_id) â€” overlap with the
            --     pujari's other ACCEPTED bookings.
            --   * ex_bookings_intended_no_overlap (intended_pujari_id, paid) â€”
            --     overlap with PAID direct bookings still awaiting this
            --     pujari's accept. Writing intended_pujari_id here is what
            --     arms this check for broadcast bookings (cross-mode hole).
            -- For direct bookings intended_pujari_id already equals the
            -- acceptor â€” the write is a no-op and cannot self-conflict.
            UPDATE bookings
            SET pujari_id          = NEW.pujari_id,
                intended_pujari_id = NEW.pujari_id,
                status_id          = v_confirmed_status_id,
                updated_at         = now()
            WHERE id = NEW.booking_id;

            INSERT INTO booking_status_history (booking_id, status_id, changed_by)
            VALUES (NEW.booking_id, v_confirmed_status_id, v_pujari_user_id);

            -- §21.6.B (migration 014): sibling live offers -> superseded.
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

CREATE TRIGGER aiu_booking_assignment_accept
    AFTER INSERT OR UPDATE ON booking_assignments
    FOR EACH ROW EXECUTE FUNCTION trg_set_booking_pujari_on_accept();

-- =============================================================================
-- TRIGGER 4 â€” promo_usage_counters (atomic check-and-increment, no app-layer race)
-- =============================================================================
CREATE OR REPLACE FUNCTION trg_enforce_promo_usage_limit() RETURNS TRIGGER AS $$
DECLARE
    v_max_uses SMALLINT;
    v_current_count SMALLINT;
BEGIN
    SELECT max_uses_per_user INTO v_max_uses FROM promo_codes WHERE id = NEW.promo_code_id;

    INSERT INTO promo_usage_counters (promo_code_id, user_id, redemption_count)
    VALUES (NEW.promo_code_id, NEW.user_id, 1)
    ON CONFLICT (promo_code_id, user_id)
    DO UPDATE SET redemption_count = promo_usage_counters.redemption_count + 1
    RETURNING redemption_count INTO v_current_count;

    IF v_current_count > v_max_uses THEN
        RAISE EXCEPTION 'Promo code usage limit exceeded for this user (max % uses)', v_max_uses;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER bi_promo_redemptions_limit_check
    BEFORE INSERT ON promo_redemptions
    FOR EACH ROW EXECUTE FUNCTION trg_enforce_promo_usage_limit();

-- =============================================================================
-- TRIGGER 5 â€” bookings.duration_minutes snapshot (window length for the
-- no-overlap exclusion constraint; frozen at booking time so a later catalog
-- change to the puja's duration never silently reshapes existing bookings)
-- =============================================================================
CREATE OR REPLACE FUNCTION trg_snapshot_booking_duration() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.duration_minutes IS NULL OR NEW.duration_minutes = 0 THEN
        SELECT COALESCE(NULLIF(duration_minutes, 0), 60) INTO NEW.duration_minutes
        FROM pujas WHERE id = NEW.puja_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER bi_bookings_duration_snapshot
    BEFORE INSERT ON bookings
    FOR EACH ROW EXECUTE FUNCTION trg_snapshot_booking_duration();
