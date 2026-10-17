"""Compare two Postgres databases (e.g. local dev vs staging).

Usage:
  python scripts/compare_database_schemas.py \\
    --left-url "$DEV_DATABASE_URL" --left-label dev \\
    --right-url "$STAGING_DATABASE_MIGRATE_URL" --right-label staging \\
    --strict

Uses read-only catalog queries; pass migrate URLs or any role with SELECT on pg_catalog.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _snapshot(url: str, label: str) -> dict:
    env = os.environ.copy()
    env["DATABASE_URL"] = url
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "verify_database_schema.py"),
            "--label",
            label,
            "--json",
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 and proc.stdout.strip():
        # verify prints JSON on last line when --json
        pass
    elif proc.returncode != 0:
        print(proc.stdout, proc.stderr, file=sys.stderr)
        raise SystemExit(f"verify failed for {label}")

    import json

    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("{")]
    if not lines:
        raise SystemExit(f"no JSON from verify for {label}")
    return json.loads(lines[-1])


def _catalog_tables(url: str) -> set[str]:
    import psycopg

    sync = (
        url.replace("postgresql+psycopg://", "postgresql://")
        .replace("postgresql+asyncpg://", "postgresql://")
    )
    with psycopg.connect(sync) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                """
            )
            return {r[0].lower() for r in cur.fetchall()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--left-url", required=True)
    parser.add_argument("--left-label", default="left")
    parser.add_argument("--right-url", required=True)
    parser.add_argument("--right-label", default="right")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    left_tables = _catalog_tables(args.left_url)
    right_tables = _catalog_tables(args.right_url)

    only_left = sorted(left_tables - right_tables)
    only_right = sorted(right_tables - left_tables)
    common = sorted(left_tables & right_tables)

    print("=== compare_database_schemas ===")
    print(f"{args.left_label}: {len(left_tables)} tables")
    print(f"{args.right_label}: {len(right_tables)} tables")
    print(f"common: {len(common)}")

    failed = False
    if only_left:
        failed = True
        print(f"ONLY {args.left_label}: {', '.join(only_left)}")
    if only_right:
        failed = True
        print(f"ONLY {args.right_label}: {', '.join(only_right)}")

    for label, url in (
        (args.left_label, args.left_url),
        (args.right_label, args.right_url),
    ):
        snap = _snapshot(url, label)
        print(f"--- verify {label} ok={snap.get('ok')} alembic={snap.get('alembic')}")
        if not snap.get("ok"):
            failed = True
            for err in snap.get("errors", []):
                print(f"  {err}")

    if args.strict and failed:
        sys.exit(1)
    if failed:
        print("compare: mismatches (use --strict to fail)")
    else:
        print("compare_database_schemas: OK — table sets match and both pass spec verify")


if __name__ == "__main__":
    main()
