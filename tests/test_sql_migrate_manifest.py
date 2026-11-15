"""G3 — every apply_migration_*.py is in the deploy manifest."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.repo_gate_only

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from sql_migrate_manifest import build_sql_migrate_steps, verify


def test_manifest_includes_latest_singles():
    steps = build_sql_migrate_steps()
    for n in (37, 38, 39):
        assert f"apply_migration_{n:03d}.py" in steps


def test_chain_before_035():
    steps = build_sql_migrate_steps()
    i_chain = steps.index("apply_migrations_028_032.py")
    i_035 = steps.index("apply_migration_035.py")
    assert i_chain < i_035


def test_verify_and_preflight_exit_zero():
    verify()
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "deploy_preflight_repo.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr or r.stdout
    assert "G3" in r.stdout