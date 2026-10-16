#!/usr/bin/env python3
"""Live deploy preflight: app URL (PgBouncer) + admin URL (pg_roles)."""

from __future__ import annotations

import os
import sys

try:
    import psycopg
except ImportError:
    print("psycopg not installed", file=sys.stderr)
    sys.exit(1)


def _normalize(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


def _ping_app_url(url: str, rounds: int = 8) -> None:
    for i in range(rounds):
        with psycopg.connect(url, prepare_threshold=None) as conn:
            conn.execute("SELECT 1")
    print(f"live: app DATABASE_URL OK ({rounds} round-trips, prepare_threshold=None)")


def _check_roles(admin_url: str) -> None:
    required = ("puja_app", "puja_migrate")
    with psycopg.connect(admin_url, prepare_threshold=None) as conn:
        found = {
            row[0]
            for row in conn.execute(
                "SELECT rolname FROM pg_roles WHERE rolname = ANY(%s)",
                (list(required),),
            ).fetchall()
        }
    missing = [r for r in required if r not in found]
    if missing:
        raise SystemExit(
            f"live FAIL: missing pg_roles {missing} — run scripts/bootstrap.sh on this DB"
        )
    print(f"live: pg_roles OK ({', '.join(required)})")


def main() -> int:
    app_url = os.environ.get("DATABASE_URL")
    admin_url = os.environ.get("DATABASE_ADMIN_URL") or os.environ.get(
        "DATABASE_MIGRATE_URL"
    )

    if not app_url:
        print("live: SKIP (DATABASE_URL not set — repo preflight only)")
        return 0

    _ping_app_url(_normalize(app_url))

    if not admin_url:
        print(
            "live: WARN DATABASE_ADMIN_URL unset — skipping pg_roles check "
            "(set superuser or migrate URL for full gate)"
        )
        return 0

    _check_roles(_normalize(admin_url))
    print("deploy_preflight_live: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
