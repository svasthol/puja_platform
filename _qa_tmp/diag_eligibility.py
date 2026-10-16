"""Check whether QA pujari is in the dispatch eligibility pool for a slot."""
from __future__ import annotations

import datetime as dt
from dotenv import load_dotenv
load_dotenv()

import psycopg
from app.core.config import get_settings
from app.services.dispatch_launch import launch_eligibility_slot_sql, load_dispatch_settings

PUJARI = "5f12ff01-8674-44c7-9f16-9a4ba7826f19"

url = str(get_settings().DATABASE_URL).replace("postgresql+psycopg://", "postgresql://")
conn = psycopg.connect(url)
cur = conn.cursor()

# puja griha-pravesham
cur.execute("SELECT id, duration_minutes FROM pujas WHERE slug='griha-pravesham' LIMIT 1")
puja_id, dur = cur.fetchone()
dur = dur or 90
slot_date = (dt.date.today() + dt.timedelta(days=20)).isoformat()

settings = load_dispatch_settings(cur)
import re
sql = re.sub(r"(?<!:):(?!:)(\w+)", r"%(\1)s", launch_eligibility_slot_sql(settings))
params = {
    "puja_id": str(puja_id),
    "scheduled_date": slot_date,
    "scheduled_time": "10:30:00",
    "duration_minutes": dur,
    "exclude_booking_id": "00000000-0000-0000-0000-000000000000",
}
cur.execute(sql, params)
rows = [str(r[0]) for r in cur.fetchall()]
print("eligible_count:", len(rows))
print("QA pujari eligible:", PUJARI in rows)

# component checks
cur.execute("SELECT verification_status FROM pujaris WHERE id=%s", (PUJARI,))
print("verification:", cur.fetchone())
cur.execute("SELECT count(*) FROM pujari_pricing WHERE pujari_id=%s AND puja_id=%s", (PUJARI, str(puja_id)))
print("pricing_rows:", cur.fetchone()[0])
cur.execute("SELECT count(*) FROM pujari_service_areas psa JOIN service_areas sa ON sa.id=psa.service_area_id AND sa.is_active WHERE psa.pujari_id=%s", (PUJARI,))
print("active_service_areas:", cur.fetchone()[0])
cur.execute("SELECT EXTRACT(ISODOW FROM %s::date)::int - 1", (slot_date,))
dow = cur.fetchone()[0]
cur.execute("SELECT count(*) FROM pujari_availability WHERE pujari_id=%s AND day_of_week=%s AND start_time<=%s AND end_time>%s", (PUJARI, dow, "10:30:00", "10:30:00"))
print(f"availability_covering (dow={dow}):", cur.fetchone()[0])
conn.close()
