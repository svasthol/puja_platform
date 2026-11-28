"""Smoke tests for scripts/validate_api_env.py."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "deploy/env/staging.api.env.example"


def test_staging_template_parses_with_placeholder_vendor():
    # Template uses REPLACE placeholders — may exit 1 on missing KYC key; must not crash on CORS parse
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts/validate_api_env.py"), str(TEMPLATE)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    combined = (proc.stdout or "") + (proc.stderr or "")
    assert "validation error" not in combined.lower() or "KYC_VENDOR" in combined
    assert "single quotes" not in combined.lower()


def test_rejects_allowed_origins_single_quotes(tmp_path):
    bad = tmp_path / "bad.env"
    bad.write_text(
        'APP_ENV=development\n'
        'SECRET_KEY=change-me-to-at-least-32-random-chars-openssl-rand-hex-32\n'
        'DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/Mana_Guruji\n'
        'ALLOWED_ORIGINS=\'["http://localhost:3000"]\'\n',
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts/validate_api_env.py"), str(bad)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "single quotes" in (proc.stderr or "").lower()