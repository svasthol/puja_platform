#!/usr/bin/env python3
"""Remove staging users (and cascaded partner/customer data) for a clean slate.

**Staging only** — refuses production. Requires an explicit confirmation flag.

Keeps catalog, platform_settings, relationship_managers, panchangam cache, and
(by default) admin accounts (+ admin_credentials).

Usage (on stg-aio-1):
  set -a && source /etc/mana-guruji/api.env && set +a
  python scripts/staging_wipe_users.py --dry-run
  python scripts/staging_wipe_users.py --confirm-wipe-staging-users

Scopes:
  --scope all              (default) every non-admin user
  --scope verified-partners  users linked to pujaris with verification_status='verified'

After wipe, consider Object Storage cleanup for orphaned KYC selfies (private bucket).

See scripts/staging_wipe_users.sql for the TRUNCATE prelude.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg

_REPO = Path(__file__).resolve().parents[1]
_SQL = Path(__file__).with_name("staging_wipe_users.sql")
_CONFIRM = "--confirm-wipe-staging-users"

_STAFF_ROLE_FILTER = """
  SELECT ur.user_id FROM user_roles ur
  JOIN roles r ON r.id = ur.role_id WHERE r.code IN ('admin', 'support')
"""

_DELETE_ALL_NON_ADMIN = f"""
DELETE FROM users u
WHERE u.id NOT IN ({_STAFF_ROLE_FILTER})
"""

_DELETE_VERIFIED_PARTNERS = f"""
DELETE FROM users u
USING pujaris p
WHERE p.user_id = u.id
  AND p.verification_status = 'verified'
  AND u.id NOT IN ({_STAFF_ROLE_FILTER})
"""


def _normalize_dsn(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://")


def _resolve_dsn(explicit: str | None) -> str:
    raw = (
        explicit
        or os.environ.get("DATABASE_MIGRATE_URL")
        or os.environ.get("DATABASE_ADMIN_URL")
        or os.environ.get("DATABASE_URL")
        or ""
    ).strip()
    if not raw:
        print(
            "Set DATABASE_MIGRATE_URL or DATABASE_URL (source api.env first).",
            file=sys.stderr,
        )
        sys.exit(2)
    return _normalize_dsn(raw)


def _require_env() -> str:
    app_env = (os.environ.get("APP_ENV") or "").strip().lower()
    if not app_env:
        try:
            sys.path.insert(0, str(_REPO))
            from dotenv import load_dotenv

            load_dotenv(_REPO / ".env")
            env_file = os.environ.get("ENV_FILE", "/etc/mana-guruji/api.env")
            if Path(env_file).is_file():
                load_dotenv(env_file, override=True)
            from app.core.config import get_settings

            app_env = get_settings().APP_ENV.lower()
        except Exception:
            app_env = ""
    return app_env


def _count(cur: psycopg.Cursor, sql: str, params: tuple = ()) -> int:
    cur.execute(sql, params)
    row = cur.fetchone()
    return int(row[0]) if row else 0


def _preview(cur: psycopg.Cursor, scope: str) -> dict[str, int]:
    admins = _count(
        cur,
        "SELECT count(DISTINCT ur.user_id) FROM user_roles ur "
        "JOIN roles r ON r.id = ur.role_id WHERE r.code = 'admin'",
    )
    total_users = _count(cur, "SELECT count(*) FROM users")
    verified_partners = _count(
        cur,
        "SELECT count(*) FROM pujaris WHERE verification_status = 'verified'",
    )
    if scope == "verified-partners":
        to_delete = _count(
            cur,
            """
            SELECT count(*)
            FROM users u
            JOIN pujaris p ON p.user_id = u.id
            WHERE p.verification_status = 'verified'
              AND u.id NOT IN (
                SELECT ur.user_id FROM user_roles ur
                JOIN roles r ON r.id = ur.role_id WHERE r.code IN ('admin', 'support')
              )
            """,
        )
    else:
        to_delete = _count(
            cur,
            """
            SELECT count(*) FROM users u
            WHERE u.id NOT IN (
              SELECT ur.user_id FROM user_roles ur
              JOIN roles r ON r.id = ur.role_id WHERE r.code IN ('admin', 'support')
            )
            """,
        )
    return {
        "users_total": total_users,
        "admins": admins,
        "verified_pujaris": verified_partners,
        "users_to_delete": to_delete,
    }


def _flush_redis() -> None:
    sys.path.insert(0, str(_REPO))
    from app.core.config import get_settings

    settings = get_settings()
    import redis

    for label, url in (
        ("cache", settings.redis_cache_url),
        ("celery", settings.redis_celery_url),
        ("presence", settings.redis_presence_url),
    ):
        r = redis.from_url(str(url), socket_connect_timeout=5)
        r.flushdb()
        print(f"Redis {label}: FLUSHDB ({url})")
    print("Restart mana-guruji-celery-worker and beat after Redis flush.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Staging user wipe (never production)")
    parser.add_argument(
        _CONFIRM,
        action="store_true",
        help="Required to apply changes (omit for --dry-run only)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print counts only; default if --confirm-wipe-staging-users omitted",
    )
    parser.add_argument(
        "--scope",
        choices=("all", "verified-partners"),
        default="all",
        help="all: remove every non-admin user; verified-partners: verified pujaris only",
    )
    parser.add_argument(
        "--include-admin",
        action="store_true",
        help="Also delete admin users (dangerous — you may lock yourself out)",
    )
    parser.add_argument("--dsn", default=None, help="Override Postgres DSN")
    parser.add_argument("--no-redis", action="store_true", help="Skip Redis FLUSHDB")
    parser.add_argument(
        "--allow-development",
        action="store_true",
        help="Allow APP_ENV=development (local testing only)",
    )
    args = parser.parse_args()
    dry_run = args.dry_run or not args.confirm_wipe_staging_users

    app_env = _require_env()
    if app_env == "production":
        print("REFUSED: APP_ENV=production", file=sys.stderr)
        return 1
    if app_env not in ("staging", "development"):
        print(
            f"REFUSED: APP_ENV={app_env!r} (only staging, or development with --allow-development)",
            file=sys.stderr,
        )
        return 1
    if app_env == "development" and not args.allow_development:
        print(
            "REFUSED: development — pass --allow-development to test locally",
            file=sys.stderr,
        )
        return 1

    dsn = _resolve_dsn(args.dsn)
    sql = _SQL.read_text(encoding="utf-8")
    delete_sql = (
        _DELETE_VERIFIED_PARTNERS
        if args.scope == "verified-partners"
        else _DELETE_ALL_NON_ADMIN
    )
    if args.include_admin:
        if args.scope == "verified-partners":
            delete_sql = """
            DELETE FROM users u
            USING pujaris p
            WHERE p.user_id = u.id AND p.verification_status = 'verified'
            """
        else:
            delete_sql = "DELETE FROM users"

    print(f"APP_ENV={app_env} scope={args.scope} dry_run={dry_run} include_admin={args.include_admin}")

    with psycopg.connect(dsn, autocommit=False) as conn:
        with conn.cursor() as cur:
            stats = _preview(cur, args.scope)
            print(
                f"users_total={stats['users_total']} admins={stats['admins']} "
                f"verified_pujaris={stats['verified_pujaris']} "
                f"users_to_delete={stats['users_to_delete']}"
            )
            if dry_run:
                print("Dry run — no changes. Pass --confirm-wipe-staging-users to apply.")
                conn.rollback()
                return 0

            cur.execute(sql)
            cur.execute(delete_sql)
            print(f"DELETE users rowcount={cur.rowcount}")
        conn.commit()

    print("PostgreSQL: staging_wipe_users.sql + user DELETE committed.")

    if not args.no_redis:
        try:
            _flush_redis()
        except Exception as exc:
            print(f"WARN: Redis flush failed: {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())