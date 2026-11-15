#!/usr/bin/env python3
"""Run idempotent SQL migrations in manifest order (called from migrate.sh)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from sql_migrate_manifest import build_sql_migrate_steps, verify


def main() -> int:
    verify()
    steps = build_sql_migrate_steps()
    for basename in steps:
        script = ROOT / "scripts" / basename
        if not script.is_file():
            print(f"run_sql_migrations: missing {script}", file=sys.stderr)
            return 1
        print(f"run_sql_migrations: {basename}")
        subprocess.run([sys.executable, str(script)], check=True)
    print("run_sql_migrations: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())