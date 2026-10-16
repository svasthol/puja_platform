from dotenv import load_dotenv
load_dotenv()
import psycopg
from app.core.config import get_settings

url = str(get_settings().DATABASE_URL).replace("postgresql+psycopg://", "postgresql://")
QA = "5f12ff01-8674-44c7-9f16-9a4ba7826f19"
c = psycopg.connect(url)
cur = c.cursor()
cur.execute(
    "SELECT count(*) FROM booking_assignments ba "
    "JOIN status_types st ON st.id=ba.status_id "
    "JOIN bookings b ON b.id=ba.booking_id "
    "WHERE ba.pujari_id=%s AND st.code='offered' AND ba.responded_at IS NULL "
    "AND ba.expires_at > now() AND b.cancelled_at IS NULL", (QA,))
print("live_offers_QA_pujari:", cur.fetchone()[0])
cur.execute("SELECT conname FROM pg_constraint WHERE conname IN "
            "('ex_bookings_pujari_no_overlap','ex_bookings_intended_no_overlap')")
print("exclusion_constraints_present:", [r[0] for r in cur.fetchall()])
# dispatch setting for advance inbox cap
cur.execute("SELECT key, value_json FROM platform_settings WHERE key ILIKE '%advance%offer%' OR key ILIKE '%inbox%'")
print("inbox_settings:", cur.fetchall())
c.close()
