"""Verify live Postgres matches spec/db (tables, extensions, alembic, core triggers).

Usage:
  set -a && source /etc/mana-guruji/api.env && set +a
  export DATABASE_URL="${DATABASE_MIGRATE_URL:-$DATABASE_URL}"
  python scripts/verify_database_schema.py --strict --label staging

Exit 0 when OK; exit 1 with report when --strict and mismatches exist.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DB_DIR = REPO_ROOT / "spec" / "db"

REQUIRED_EXTENSIONS = frozenset({"postgis", "pgcrypto", "btree_gist"})
ALEMBIC_HEAD = "011"

TABLE_RE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-z_][a-z0-9_]*)",
    re.IGNORECASE,
)
TRIGGER_RE = re.compile(
    r"CREATE\s+TRIGGER\s+([a-z_][a-z0-9_]*)",
    re.IGNORECASE,
)

# Base triggers.sql (migration 014 replaces function body but keeps trigger name)
BASE_TRIGGERS = frozenset(
    {
        "bi_payment_splits_net_amount",
        "aiud_reviews_rating_sync",
        "aiu_booking_assignment_accept",
        "bi_promo_redemptions_limit_check",
        "bi_bookings_duration_snapshot",
    }
)
MIGRATION_TRIGGERS = frozenset(
    {
        "bu_bookings_cancel_guard",
        "trg_addresses_geom_sync",
        "trg_refunds_cap_total",
    }
)
REQUIRED_TRIGGERS = BASE_TRIGGERS | MIGRATION_TRIGGERS

SEED_STATUS_CODES = frozenset(
    {
        ("assignment", "offered"),
        ("assignment", "accepted"),
        ("assignment", "rejected"),
        ("assignment", "expired"),
        ("assignment", "superseded"),
        ("booking", "payment_pending"),
        ("booking", "requested"),
        ("booking", "confirmed"),
        ("booking", "in_progress"),
        ("booking", "completed"),
        ("booking", "cancelled"),
        ("booking", "abandoned"),
        ("booking", "failed_no_pujari"),
        ("booking", "disputed"),
    }
)


def _sync_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("verify_database_schema: set DATABASE_URL or DATABASE_MIGRATE_URL", file=sys.stderr)
        sys.exit(2)
    return (
        url.replace("postgresql+psycopg://", "postgresql://")
        .replace("postgresql+asyncpg://", "postgresql://")
    )


def load_expected_tables() -> set[str]:
    tables: set[str] = set()
    paths = [DB_DIR / "schema.sql"] + sorted(DB_DIR.glob("migration_*.sql"))
    for path in paths:
        text = path.read_text(encoding="utf-8-sig")
        for match in TABLE_RE.finditer(text):
            tables.add(match.group(1).lower())
    return tables


def load_expected_triggers_from_spec() -> set[str]:
    found: set[str] = set()
    for path in [DB_DIR / "triggers.sql", DB_DIR / "migration_002.sql", DB_DIR / "migration_005.sql"]:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8-sig")
        for match in TRIGGER_RE.finditer(text):
            found.add(match.group(1).lower())
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify DB schema against spec/db")
    parser.add_argument("--strict", action="store_true", help="Exit 1 on any mismatch")
    parser.add_argument("--label", default="database", help="Label in report (e.g. staging, dev)")
    parser.add_argument("--json", action="store_true", help="Machine-readable summary line")
    args = parser.parse_args()

    try:
        import psycopg
    except ImportError:
        print("psycopg not installed", file=sys.stderr)
        sys.exit(2)

    expected_tables = load_expected_tables()
    spec_triggers = load_expected_triggers_from_spec()
    errors: list[str] = []
    warnings: list[str] = []

    with psycopg.connect(_sync_url()) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), current_user")
            db_name, db_user = cur.fetchone()

            cur.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                ORDER BY 1
                """
            )
            live_tables = {r[0].lower() for r in cur.fetchall()}

            cur.execute(
                "SELECT extname FROM pg_extension WHERE extname = ANY(%s)",
                (list(REQUIRED_EXTENSIONS),),
            )
            live_ext = {r[0] for r in cur.fetchall()}

            cur.execute("SELECT version_num FROM alembic_version LIMIT 1")
            row = cur.fetchone()
            alembic_ver = row[0] if row else None

            cur.execute(
                """
                SELECT t.tgname
                FROM pg_trigger t
                JOIN pg_class c ON c.oid = t.tgrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND NOT t.tgisinternal
                """
            )
            live_triggers = {r[0].lower() for r in cur.fetchall()}

            cur.execute("SELECT domain, code FROM status_types")
            live_status = {(r[0], r[1]) for r in cur.fetchall()}

    missing_tables = sorted(expected_tables - live_tables)
    extra_tables = sorted(live_tables - expected_tables - {"spatial_ref_sys"})
    missing_ext = sorted(REQUIRED_EXTENSIONS - live_ext)
    missing_triggers = sorted(REQUIRED_TRIGGERS - live_triggers)
    extra_triggers = sorted(live_triggers - REQUIRED_TRIGGERS - spec_triggers)
    missing_seed = sorted(SEED_STATUS_CODES - live_status)

    if missing_tables:
        errors.append(f"missing tables ({len(missing_tables)}): {', '.join(missing_tables)}")
    if extra_tables:
        warnings.append(f"extra tables ({len(extra_tables)}): {', '.join(extra_tables)}")
    if missing_ext:
        errors.append(f"missing extensions: {', '.join(missing_ext)}")
    if alembic_ver != ALEMBIC_HEAD:
        errors.append(f"alembic_version={alembic_ver!r} expected {ALEMBIC_HEAD}")
    if missing_triggers:
        errors.append(f"missing triggers: {', '.join(missing_triggers)}")
    if missing_seed:
        errors.append(
            f"missing status_types seed rows ({len(missing_seed)}): "
            + ", ".join(f"{d}/{c}" for d, c in missing_seed[:8])
            + ("..." if len(missing_seed) > 8 else "")
        )

    print(f"=== verify_database_schema [{args.label}] ===")
    print(f"database={db_name} user={db_user}")
    print(f"expected_tables={len(expected_tables)} live_tables={len(live_tables)}")
    print(f"extensions={sorted(live_ext)} alembic={alembic_ver}")
    print(f"triggers_live={len(live_triggers)} status_types_rows={len(live_status)}")

    for w in warnings:
        print(f"WARN: {w}")
    for e in errors:
        print(f"FAIL: {e}")

    ok = not errors
    import json

    payload = {
        "label": args.label,
        "ok": ok,
        "errors": errors,
        "warnings": warnings,
        "table_count": len(live_tables),
        "expected_table_count": len(expected_tables),
        "alembic": alembic_ver,
    }
    if args.json:
        print(json.dumps(payload))

    if args.strict and not ok:
        sys.exit(1)
    if not ok and not args.strict:
        print("verify_database_schema: issues found (run with --strict to fail CI)")
    else:
        print("verify_database_schema: OK")


if __name__ == "__main__":
    main()
