"""Compare two Postgres databases (e.g. local dev vs staging).

Deep mode (default): tables, columns, constraints, indexes, triggers, sequences, extensions.
Read-only catalog queries only.

Usage:
  python scripts/compare_database_schemas.py \\
    --left-url "$DEV_DATABASE_URL" --left-label dev \\
    --right-url "postgresql://puja_migrate@127.0.0.1:15432/Mana_Guruji" --right-label staging \\
    --strict

  python scripts/compare_database_schemas.py ... --json-out report.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from db_schema_catalog import (  # noqa: E402
    diff_catalogs,
    fetch_catalog,
    print_diff_report,
)


def _spec_verify(url: str, label: str) -> dict:
    env = __import__("os").environ.copy()
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
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("{")]
    if not lines:
        if proc.stderr:
            print(proc.stderr, file=sys.stderr)
        if proc.stdout:
            print(proc.stdout, file=sys.stderr)
        raise SystemExit(f"verify_database_schema failed for {label} (exit {proc.returncode})")
    return json.loads(lines[-1])


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two Postgres schemas (read-only)")
    parser.add_argument("--left-url", required=True)
    parser.add_argument("--left-label", default="left")
    parser.add_argument("--right-url", required=True)
    parser.add_argument("--right-label", default="right")
    parser.add_argument("--strict", action="store_true", help="Exit 1 on any mismatch")
    parser.add_argument(
        "--skip-spec-verify",
        action="store_true",
        help="Skip spec/db verify per side (catalog diff only)",
    )
    parser.add_argument("--json-out", type=Path, help="Write diff JSON to file")
    parser.add_argument(
        "--export-catalogs",
        nargs=2,
        metavar=("LEFT_JSON", "RIGHT_JSON"),
        help="Write full left/right catalogs (all columns, constraints, indexes)",
    )
    parser.add_argument(
        "--inventory-md",
        nargs=2,
        metavar=("LEFT_MD", "RIGHT_MD"),
        help="Write human-readable per-table markdown inventories",
    )
    args = parser.parse_args()

    print("compare_database_schemas: fetching catalogs (read-only)...")
    left_cat = fetch_catalog(args.left_url)
    right_cat = fetch_catalog(args.right_url)
    diff = diff_catalogs(left_cat, right_cat, args.left_label, args.right_label)
    print_diff_report(diff, left_cat, right_cat, args.left_label, args.right_label)

    spec_failed = False
    if not args.skip_spec_verify:
        for label, url in (
            (args.left_label, args.left_url),
            (args.right_label, args.right_url),
        ):
            snap = _spec_verify(url, label)
            print(f"--- spec/db verify [{label}] ok={snap.get('ok')} alembic={snap.get('alembic')}")
            if not snap.get("ok"):
                spec_failed = True
                for err in snap.get("errors", []):
                    print(f"  spec FAIL: {err}")

    if args.export_catalogs:
        left_path, right_path = Path(args.export_catalogs[0]), Path(args.export_catalogs[1])
        left_path.write_text(json.dumps(left_cat, indent=2), encoding="utf-8")
        right_path.write_text(json.dumps(right_cat, indent=2), encoding="utf-8")
        print(f"Wrote catalogs: {left_path} , {right_path}")

    if args.inventory_md:
        from db_schema_inventory import to_markdown  # noqa: E402

        lp, rp = Path(args.inventory_md[0]), Path(args.inventory_md[1])
        lp.write_text(to_markdown(left_cat, args.left_label), encoding="utf-8")
        rp.write_text(to_markdown(right_cat, args.right_label), encoding="utf-8")
        print(f"Wrote inventories: {lp} , {rp}")

    if args.json_out:
        from db_schema_catalog import catalog_stats  # noqa: E402

        payload = {
            "diff": diff.to_dict(),
            "coverage": {
                args.left_label: catalog_stats(left_cat),
                args.right_label: catalog_stats(right_cat),
            },
            "spec_verify_failed": spec_failed,
        }
        args.json_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote {args.json_out}")

    failed = not diff.ok or spec_failed
    if failed:
        print("compare_database_schemas: MISMATCH")
        if not diff.ok:
            print(
                "Remediation (safe): bring staging in line with repo — "
                "on stg-aio-1 run ./scripts/migrate.sh (never copy dev data)."
            )
    else:
        print("compare_database_schemas: OK — catalogs match and spec verify passed")

    if args.strict and failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
