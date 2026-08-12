"""Backfill pujari_pricing for active catalogue pujas (run after admin adds a puja)."""
from __future__ import annotations

import psycopg
import sys

DSN = sys.argv[1] if len(sys.argv) > 1 else "postgresql://postgres:Mahadeva123@localhost:5432/Mana_Guruji"

SQL = """
INSERT INTO pujari_pricing (id, pujari_id, puja_id, base_price)
SELECT gen_random_uuid(), pj.id, p.id, p.default_price
FROM pujas p
CROSS JOIN pujaris pj
WHERE p.is_active = true
  AND pj.verification_status = 'verified'
  AND NOT EXISTS (
    SELECT 1 FROM pujari_pricing pp
    WHERE pp.pujari_id = pj.id AND pp.puja_id = p.id
  )
RETURNING puja_id, pujari_id
"""

if __name__ == "__main__":
    conn = psycopg.connect(DSN)
    cur = conn.cursor()
    cur.execute(SQL)
    rows = cur.fetchall()
    conn.commit()
    print(f"Inserted {len(rows)} pujari_pricing row(s)")
    for r in rows:
        print(" ", r)
    conn.close()
