"""Safe remediation plan for dev vs staging schema drift.

Does NOT apply arbitrary DDL from dev to staging. Allowed actions:
  plan (default) — print recommended steps only
  staging-migrate — run migrate.sh on staging host via SSH (idempotent repo migrations)

Never drops tables/columns or copies dev row data.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from db_schema_catalog import diff_catalogs, fetch_catalog  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Safe staging schema sync plan / migrate")
    parser.add_argument("--dev-url", required=True)
    parser.add_argument("--staging-url", required=True)
    parser.add_argument(
        "--action",
        choices=("plan", "staging-migrate"),
        default="plan",
        help="plan=report only; staging-migrate=SSH migrate on staging VM",
    )
    parser.add_argument("--staging-ssh", default="opc@140.245.245.201", help="SSH target for migrate")
    parser.add_argument(
        "--repo-on-staging",
        default="/opt/mana-guruji/src/puja_platform",
        help="Path to puja_platform on staging VM",
    )
    parser.add_argument("--yes", action="store_true", help="Required for staging-migrate")
    args = parser.parse_args()

    left = fetch_catalog(args.dev_url)
    right = fetch_catalog(args.staging_url)
    diff = diff_catalogs(left, right, "dev", "staging")

    print("=== db_parity_sync ===")
    if diff.ok:
        print("Catalogs match — no migrate required for structure parity.")
        return

    print("Drift detected. Safe sync path:")
    print("  1. git pull dev on staging VM")
    print("  2. ./scripts/migrate.sh (Alembic + 012–034 + apply_grants)")
    print("  3. Re-run compare_database_schemas.py")
    print("")
    print("NOT performed automatically: DROP, dev→staging pg_dump schema, data copy.")

    if args.action == "plan":
        print("Action=plan — no changes made.")
        sys.exit(1 if not diff.ok else 0)

    if not args.yes:
        print("Refusing staging-migrate without --yes", file=sys.stderr)
        sys.exit(2)

    cmd = [
        "ssh",
        args.staging_ssh,
        f"set -euo pipefail; cd {args.repo_on_staging}; git pull origin dev; ./scripts/migrate.sh",
    ]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)
    print("staging-migrate: done — re-run compare to confirm.")


if __name__ == "__main__":
    main()
