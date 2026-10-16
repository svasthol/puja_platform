#!/usr/bin/env python3
"""Repo-side deploy preflight (G1/G2). Exit 1 if required code/bootstrap artifacts missing."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def check_g1_engine() -> None:
    text = _read(ROOT / "app/db/engine.py")
    if "prepare_threshold" not in text or "connect_args" not in text:
        raise SystemExit("G1 FAIL: app/db/engine.py missing connect_args prepare_threshold")
    if re.search(r"prepare_threshold\s*:\s*None", text) is None and re.search(
        r"['\"]prepare_threshold['\"]\s*:\s*None", text
    ) is None:
        raise SystemExit("G1 FAIL: engine.py prepare_threshold=None not found")


def check_g1_sweep() -> None:
    text = _read(ROOT / "app/workers/sweep.py")
    if re.search(r"prepare_threshold\s*=\s*None", text) is None:
        raise SystemExit("G1 FAIL: sweep.get_connection() missing prepare_threshold=None")


def check_g2_bootstrap() -> None:
    bootstrap = ROOT / "scripts/bootstrap.sh"
    if not bootstrap.is_file():
        raise SystemExit("G2 FAIL: scripts/bootstrap.sh missing")
    btext = bootstrap.read_text(encoding="utf-8")
    if "bootstrap_puja_migrate_role" not in btext:
        raise SystemExit("G2 FAIL: bootstrap.sh must call bootstrap_puja_migrate_role.py")
    sql = _read(ROOT / "scripts/bootstrap_puja_migrate_role.sql")
    if "puja_migrate" not in sql:
        raise SystemExit("G2 FAIL: bootstrap_puja_migrate_role.sql missing puja_migrate")
    py = _read(ROOT / "scripts/bootstrap_puja_migrate_role.py")
    if "ALTER DEFAULT PRIVILEGES" not in py:
        raise SystemExit("G2 FAIL: bootstrap_puja_migrate_role.py missing default privileges")


def main() -> int:
    check_g1_engine()
    check_g1_sweep()
    check_g2_bootstrap()
    print("deploy_preflight_repo: G1 + G2 OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
