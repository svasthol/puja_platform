-- Migration 033 — TDS v3 amount split: online + offline + tds_collected_online = total (chains after 032).

ALTER TABLE bookings DROP CONSTRAINT IF EXISTS ck_bookings_amount_split;
ALTER TABLE bookings ADD CONSTRAINT ck_bookings_amount_split
    CHECK (
        amount_due_online + amount_due_offline + COALESCE(tds_collected_online, 0) = total_amount
    );

COMMENT ON CONSTRAINT ck_bookings_amount_split ON bookings IS
    'TDS v3: platform online TDS (tds_collected_online) plus offline due equals puja total_amount.';
