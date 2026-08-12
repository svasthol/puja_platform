"""Verify migration 009 objects on the DATABASE_URL database.

Usage:  python scripts/check_migration_009.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

CHECKS = [
    (
        "auth_sessions.refresh_jti column",
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name='auth_sessions' AND column_name='refresh_jti'",
    ),
    (
        "ux_auth_sessions_refresh_jti index",
        "SELECT 1 FROM pg_indexes WHERE indexname='ux_auth_sessions_refresh_jti'",
    ),
    ("roles seeded: admin", "SELECT 1 FROM roles WHERE name='admin'"),
    ("roles seeded: support", "SELECT 1 FROM roles WHERE name='support'"),
    (
        "status ('assignment','revoked')",
        "SELECT 1 FROM status_types WHERE domain='assignment' AND code='revoked'",
    ),
    ("admin_audit_log table", "SELECT 1 FROM pg_tables WHERE tablename='admin_audit_log'"),
    ("admin_credentials table", "SELECT 1 FROM pg_tables WHERE tablename='admin_credentials'"),
    (
        "promo_codes date CHECK",
        "SELECT 1 FROM pg_constraint WHERE conname='ck_promo_codes_valid_range' AND convalidated",
    ),
    ("alembic at 009", "SELECT 1 FROM alembic_version WHERE version_num='009'"),
]


def main() -> int:
    url = os.environ["DATABASE_URL"].replace("+psycopg", "")
    failed = 0
    with psycopg.connect(url) as conn, conn.cursor() as cur:
        for label, sql in CHECKS:
            cur.execute(sql)
            ok = cur.fetchone() is not None
            print(f"  {'OK ' if ok else 'FAIL'}  {label}")
            failed += 0 if ok else 1
        cur.execute("SELECT rolname FROM pg_roles WHERE rolname='puja_app'")
        has_role = cur.fetchone() is not None
        print(
            f"  {'OK ' if has_role else 'WARN'}  puja_app role "
            f"{'exists' if has_role else 'missing (dev) - grants skipped; prod MUST run scripts/apply_grants.sql'}"
        )
    print("\nmigration 009:", "VERIFIED" if failed == 0 else f"{failed} CHECK(S) FAILED")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
