"""Backfill verified pujaris for dispatch supply (availability + service area links).

Run after `sync_active_puja_pricing.py` when checkout returns NO_DISPATCH_SUPPLY.
Production path: `app/services/partner_dispatch_readiness.py` runs automatically on KYC verify.
This script remains for one-off DB repair on existing verified pujaris.
"""
from __future__ import annotations

import sys

import psycopg

DSN = (
    sys.argv[1]
    if len(sys.argv) > 1
    else "postgresql://postgres:Mahadeva123@localhost:5432/Mana_Guruji"
)

ENSURE_SERVICE_AREA = """
INSERT INTO service_areas (city, zone_name, is_active)
VALUES ('Hyderabad', 'Default', true)
ON CONFLICT (city, zone_name) DO NOTHING
"""

LINK_SERVICE_AREAS = """
INSERT INTO pujari_service_areas (pujari_id, service_area_id)
SELECT pj.id, sa.id
FROM pujaris pj
CROSS JOIN service_areas sa
WHERE pj.verification_status = 'verified'
  AND sa.is_active = true
  AND NOT EXISTS (
    SELECT 1 FROM pujari_service_areas psa
    WHERE psa.pujari_id = pj.id AND psa.service_area_id = sa.id
  )
RETURNING pujari_id, service_area_id
"""

ENSURE_AVAILABILITY = """
INSERT INTO pujari_availability (id, pujari_id, day_of_week, start_time, end_time)
SELECT gen_random_uuid(), pj.id, dow.d, '06:00'::time, '23:59'::time
FROM pujaris pj
CROSS JOIN generate_series(0, 6) AS dow(d)
WHERE pj.verification_status = 'verified'
  AND NOT EXISTS (
    SELECT 1 FROM pujari_availability pa
    WHERE pa.pujari_id = pj.id AND pa.day_of_week = dow.d
  )
RETURNING pujari_id, day_of_week
"""

WIDE_AVAILABILITY = """
UPDATE pujari_availability pa
SET start_time = '06:00', end_time = '23:59'
FROM pujaris pj
WHERE pa.pujari_id = pj.id
  AND pj.verification_status = 'verified'
  AND (pa.start_time <> '06:00'::time OR pa.end_time <> '23:59'::time)
RETURNING pa.pujari_id, pa.day_of_week
"""


def main() -> None:
    with psycopg.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(ENSURE_SERVICE_AREA)
            cur.execute(LINK_SERVICE_AREAS)
            area_links = cur.fetchall()
            cur.execute(ENSURE_AVAILABILITY)
            avail_ins = cur.fetchall()
            cur.execute(WIDE_AVAILABILITY)
            avail_upd = cur.fetchall()
        conn.commit()
    print(f"Linked {len(area_links)} pujari_service_areas row(s)")
    print(f"Inserted {len(avail_ins)} pujari_availability row(s)")
    print(f"Widened {len(avail_upd)} pujari_availability row(s)")


if __name__ == "__main__":
    main()
