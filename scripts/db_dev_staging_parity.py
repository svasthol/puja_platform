"""Laptop orchestrator: SSH tunnel → compare dev vs staging → optional safe sync.

Staging Postgres listens on 127.0.0.1:5432 on the VM — use a tunnel, not public :5432.

Example (PowerShell):
  $env:DEV_DATABASE_URL = "postgresql://postgres@127.0.0.1:5432/Mana_Guruji"
  $env:STAGING_DATABASE_URL = "postgresql://puja_migrate:SECRET@127.0.0.1:15432/Mana_Guruji"
  python scripts/db_dev_staging_parity.py --ensure-tunnel --compare --strict

Optional: --update-ingress for API :8000 / admin :3000 only (not Postgres).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from staging_db_tunnel import (  # noqa: E402
    DEFAULT_LOCAL_PORT,
    DEFAULT_SSH_TARGET,
    ensure_tunnel,
    resolve_staging_url,
)

TF_ENV = REPO_ROOT / "infra" / "oci" / "terraform" / "environments" / "staging"


def _run(cmd: list[str], **kwargs) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True, **kwargs)


def main() -> None:
    parser = argparse.ArgumentParser(description="Dev laptop ↔ staging DB parity pipeline")
    parser.add_argument("--dev-url", default=os.environ.get("DEV_DATABASE_URL", ""))
    parser.add_argument(
        "--staging-url",
        default=os.environ.get("STAGING_DATABASE_URL", os.environ.get("STAGING_DATABASE_MIGRATE_URL", "")),
    )
    parser.add_argument(
        "--update-ingress",
        action="store_true",
        help="terraform apply developer /32 (API/admin ports; not Postgres)",
    )
    parser.add_argument(
        "--ensure-tunnel",
        action="store_true",
        help=f"ssh -L <port>:127.0.0.1:5432 (default local port {DEFAULT_LOCAL_PORT})",
    )
    parser.add_argument("--staging-ssh", default=os.environ.get("STAGING_SSH", DEFAULT_SSH_TARGET))
    parser.add_argument(
        "--tunnel-local-port",
        type=int,
        default=int(os.environ.get("STAGING_DB_TUNNEL_PORT", str(DEFAULT_LOCAL_PORT))),
    )
    parser.add_argument("--compare", action="store_true", help="Run deep compare")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument(
        "--sync",
        choices=("none", "plan", "staging-migrate"),
        default="none",
        help="Safe sync; staging-migrate needs --yes",
    )
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--skip-terraform", action="store_true", help="Only refresh tfvars CIDR, no apply")
    args = parser.parse_args()

    if args.update_ingress:
        cidr_proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "oci_public_cidr.py")],
            capture_output=True,
            text=True,
            check=True,
        )
        cidr = cidr_proc.stdout.strip()
        print(f"developer CIDR: {cidr}")
        tfvars = TF_ENV / "developer.auto.tfvars.json"
        tfvars.write_text(
            f'{{"developer_allowed_cidrs":["{cidr}"]}}\n',
            encoding="utf-8",
        )
        print(f"Wrote {tfvars}")
        if not args.skip_terraform:
            _run(
                ["terraform", "apply", "-auto-approve", "-input=false"],
                cwd=str(TF_ENV),
            )
        print(
            "Ingress is for app ports (8000/3000/6379). Postgres stays on VM localhost — use --ensure-tunnel."
        )

    if args.ensure_tunnel:
        ensure_tunnel(args.staging_ssh, args.tunnel_local_port)

    staging_url = resolve_staging_url(args.staging_url or None, args.tunnel_local_port)

    if not args.dev_url or not staging_url:
        if args.compare or args.sync != "none":
            print(
                "Set DEV_DATABASE_URL and STAGING_DATABASE_URL (127.0.0.1:TUNNEL_PORT) "
                "or STAGING_DB_PASSWORD + --ensure-tunnel.",
                file=sys.stderr,
            )
            sys.exit(2)
        return

    if args.compare:
        cmd = [
            sys.executable,
            str(REPO_ROOT / "scripts" / "compare_database_schemas.py"),
            "--left-url",
            args.dev_url,
            "--left-label",
            "dev",
            "--right-url",
            staging_url,
            "--right-label",
            "staging",
        ]
        if args.strict:
            cmd.append("--strict")
        if args.json_out:
            cmd.extend(["--json-out", str(args.json_out)])
        proc = subprocess.run(cmd)
        if proc.returncode != 0 and args.sync == "none":
            sys.exit(proc.returncode)

    if args.sync != "none":
        sync_cmd = [
            sys.executable,
            str(REPO_ROOT / "scripts" / "db_parity_sync.py"),
            "--dev-url",
            args.dev_url,
            "--staging-url",
            staging_url,
            "--action",
            "staging-migrate" if args.sync == "staging-migrate" else "plan",
        ]
        if args.yes:
            sync_cmd.append("--yes")
        proc = subprocess.run(sync_cmd)
        sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
