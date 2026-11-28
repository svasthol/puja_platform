"""emit_api_env_exports.py must handle JSON list values (bash-unsafe in bare source)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_emit_quotes_allowed_origins(tmp_path):
    env = tmp_path / "t.env"
    env.write_text(
        'APP_ENV=staging\n'
        'ALLOWED_ORIGINS=["http://localhost:3000"]\n'
        'TOTP_ISSUER=Mana Guruji\n'
        'SMS_PROVIDER_ORDER=fast2sms,msg91\n',
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts/linux/emit_api_env_exports.py"), str(env)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    out = proc.stdout
    assert 'ALLOWED_ORIGINS=' in out
    assert "localhost:3000" in out
    assert "TOTP_ISSUER=" in out
    assert "Mana Guruji" in out