-- Migration 005 — refund cap + address geom sync (v3.2)
-- Apply after 004. See spec/plans/SPEC_AMENDMENTS.md and spec/DATABASE.md.

-- ---- addresses: keep geom in sync with lat/lng ---------------------------
CREATE OR REPLACE FUNCTION trg_fn_addresses_geom_sync()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.latitude IS NOT NULL AND NEW.longitude IS NOT NULL THEN
        NEW.geom := ST_SetSRID(
            ST_MakePoint(NEW.longitude::double precision, NEW.latitude::double precision),
            4326
        )::geography;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_addresses_geom_sync ON addresses;
CREATE TRIGGER trg_addresses_geom_sync
    BEFORE INSERT OR UPDATE OF latitude, longitude ON addresses
    FOR EACH ROW EXECUTE FUNCTION trg_fn_addresses_geom_sync();

-- Backfill existing rows that have lat/lng but null geom
UPDATE addresses
SET geom = ST_SetSRID(ST_MakePoint(longitude::double precision, latitude::double precision), 4326)::geography
WHERE latitude IS NOT NULL AND longitude IS NOT NULL AND geom IS NULL;

-- ---- refunds: cap total succeeded refunds per payment --------------------
CREATE OR REPLACE FUNCTION trg_fn_refunds_cap_total()
RETURNS TRIGGER AS $$
DECLARE
    v_payment_amount DECIMAL(10,2);
    v_refunded       DECIMAL(10,2);
BEGIN
    SELECT amount INTO v_payment_amount FROM payments WHERE id = NEW.payment_id;
    IF v_payment_amount IS NULL THEN
        RAISE EXCEPTION 'refunds: payment_id % not found', NEW.payment_id;
    END IF;
    SELECT COALESCE(SUM(amount), 0) INTO v_refunded
    FROM refunds
    WHERE payment_id = NEW.payment_id
      AND status = 'succeeded'
      AND id IS DISTINCT FROM NEW.id;
    IF v_refunded + NEW.amount > v_payment_amount THEN
        RAISE EXCEPTION 'refunds: total refunded % + % exceeds payment amount %',
            v_refunded, NEW.amount, v_payment_amount;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_refunds_cap_total ON refunds;
CREATE TRIGGER trg_refunds_cap_total
    BEFORE INSERT OR UPDATE OF amount, status ON refunds
    FOR EACH ROW
    WHEN (NEW.status IN ('pending', 'processing', 'succeeded'))
    EXECUTE FUNCTION trg_fn_refunds_cap_total();
