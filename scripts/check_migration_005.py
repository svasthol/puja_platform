"""One-off: verify migration 005 objects exist. No secrets printed."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

url = os.environ.get("DATABASE_URL")
if not url:
    print("NO_DATABASE_URL")
    sys.exit(1)

import psycopg

for p in ("+psycopg", "+psycopg2"):
    url = url.replace(p, "")

with psycopg.connect(url) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT version_num FROM alembic_version")
        print("alembic_version:", cur.fetchone()[0])

        cur.execute(
            """
            SELECT tgname FROM pg_trigger t
            JOIN pg_class c ON c.oid = t.tgrelid
            WHERE c.relname = 'refunds' AND NOT t.tgisinternal
            ORDER BY tgname
            """
        )
        print("refunds_triggers:", [r[0] for r in cur.fetchall()])

        cur.execute(
            """
            SELECT proname FROM pg_proc
            WHERE proname IN ('trg_fn_refunds_cap_total', 'trg_fn_addresses_geom_sync')
            ORDER BY proname
            """
        )
        print("migration_005_functions:", [r[0] for r in cur.fetchall()])

        cur.execute(
            """
            SELECT 1 FROM pg_trigger t
            JOIN pg_class c ON c.oid = t.tgrelid
            WHERE c.relname = 'addresses' AND t.tgname = 'trg_addresses_geom_sync'
            """
        )
        print("addresses_geom_trigger:", "yes" if cur.fetchone() else "no")

        cur.execute(
            """
            SELECT 1 FROM pg_trigger t
            JOIN pg_class c ON c.oid = t.tgrelid
            WHERE c.relname = 'refunds' AND t.tgname = 'trg_refunds_cap_total'
            """
        )
        cap = cur.fetchone() is not None
        print("refund_cap_trigger:", "yes" if cap else "no")
        print("migration_005_applied:", "yes" if cap else "no")
