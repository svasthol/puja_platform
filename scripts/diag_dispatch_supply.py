"""Diagnose dispatch supply — standalone (no app imports)."""
from __future__ import annotations

import datetime as dt
import os
import re
import sys

import psycopg

ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")


def load_database_url() -> str:
    with open(ENV_PATH, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"^DATABASE_URL=(.+)$", line.strip())
            if m:
                url = m.group(1).strip().strip('"')
                return url.replace("postgresql+psycopg://", "postgresql://").replace(
                    "postgresql+asyncpg://", "postgresql://"
                )
    raise RuntimeError("DATABASE_URL not found in .env")


# Defaults from LaunchDispatchSettings / config.py
REOFFER_COOLDOWN_MINUTES = 45
DISPATCH_BUFFER_MINUTES = 60


def eligibility_sql() -> str:
    return f"""
        SELECT pj.id
        FROM (
            SELECT
                CAST(%(puja_id)s AS uuid) AS puja_id,
                CAST(%(scheduled_date)s AS date) AS scheduled_date,
                CAST(%(scheduled_time)s AS time) AS scheduled_time,
                CAST(%(duration_minutes)s AS int) AS duration_minutes,
                CAST(%(exclude_booking_id)s AS uuid) AS id
        ) b
        JOIN pujaris pj ON pj.verification_status = 'verified'
        JOIN pujari_pricing pp ON pp.pujari_id = pj.id AND pp.puja_id = b.puja_id
        JOIN pujari_service_areas psa ON psa.pujari_id = pj.id
        JOIN service_areas sa ON sa.id = psa.service_area_id AND sa.is_active
        WHERE TRUE
          AND EXISTS (
            SELECT 1 FROM pujari_availability pa
            WHERE pa.pujari_id = pj.id
              AND pa.day_of_week = (EXTRACT(ISODOW FROM b.scheduled_date)::int - 1)
              AND pa.start_time <= b.scheduled_time
              AND pa.end_time > b.scheduled_time
          )
          AND NOT EXISTS (
            SELECT 1 FROM pujari_unavailability pu
            WHERE pu.pujari_id = pj.id AND pu.unavailable_date = b.scheduled_date
          )
    """


def count_step(cur, base_params: dict, extra: str) -> int:
    sql = eligibility_sql() + extra
    cur.execute(sql, base_params)
    return len(cur.fetchall())


def main() -> None:
    dsn = sys.argv[1] if len(sys.argv) > 1 else load_database_url()
    sql = eligibility_sql()

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            print("=== Verified pujaris ===")
            cur.execute(
                """
        SELECT pj.id, pj.verification_status,
               (SELECT count(*) FROM pujari_pricing pp WHERE pp.pujari_id = pj.id) AS pricing_rows,
               (SELECT count(*) FROM pujari_availability pa WHERE pa.pujari_id = pj.id) AS avail_rows,
               (SELECT count(*) FROM pujari_service_areas psa WHERE psa.pujari_id = pj.id) AS area_rows
        FROM pujaris pj
                """
            )
            cols = [d[0] for d in cur.description]
            for row in cur.fetchall():
                print(dict(zip(cols, row)))

            cur.execute(
                """
                SELECT p.id, p.name, p.duration_minutes
                FROM pujas p
                WHERE p.is_active AND EXISTS (
                  SELECT 1 FROM pujari_pricing pp
                  JOIN pujaris pj ON pj.id = pp.pujari_id AND pj.verification_status = 'verified'
                  WHERE pp.puja_id = p.id
                )
                ORDER BY p.name LIMIT 1
                """
            )
            puja = cur.fetchone()
            if not puja:
                print("\nNo catalog-visible puja — run scripts/sync_active_puja_pricing.py")
                return

            puja_id, puja_name, duration = puja
            print(f"\n=== Slot scan: {puja_name} ({puja_id}) duration={duration}m ===")

            for days_ahead in range(0, 8):
                slot_date = dt.date.today() + dt.timedelta(days=days_ahead)
                isodow = slot_date.isoweekday()
                for slot_time in ("09:00:00", "10:00:00", "14:00:00", "18:00:00"):
                    params = {
                        "puja_id": str(puja_id),
                        "scheduled_date": slot_date,
                        "scheduled_time": slot_time,
                        "duration_minutes": duration,
                        "exclude_booking_id": "00000000-0000-0000-0000-000000000000",
                    }
                    cur.execute(sql, params)
                    rows = cur.fetchall()
                    mark = "OK" if rows else "ZERO"
                    names = ", ".join(str(r[0]) for r in rows) if rows else "-"
                    print(
                        f"  [{mark}] {slot_date} dow={isodow} pa_dow={isodow-1} "
                        f"{slot_time} n={len(rows)} {names}"
                    )

            print("\n=== pujari_availability (verified) ===")
            cur.execute(
                """
        SELECT pj.id, pa.day_of_week, pa.start_time, pa.end_time
        FROM pujari_availability pa
        JOIN pujaris pj ON pj.id = pa.pujari_id
        WHERE pj.verification_status = 'verified'
        ORDER BY pj.id, pa.day_of_week, pa.start_time
                """
            )
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
            if not rows:
                print("NONE — root cause: no availability windows configured")
            for row in rows:
                print(dict(zip(cols, row)))

            print("\n=== active service_areas ===")
            cur.execute("SELECT id, name, is_active FROM service_areas ORDER BY name")
            cols = [d[0] for d in cur.description]
            for row in cur.fetchall():
                print(dict(zip(cols, row)))


if __name__ == "__main__":
    main()
