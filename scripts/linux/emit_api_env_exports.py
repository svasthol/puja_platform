#!/usr/bin/env python3
"""Print POSIX-safe export lines for a dotenv file (for bash set -a source).

api.env is parsed by systemd and pydantic — not valid bash. Deploy/migrate must
not use bare ``source api.env`` (brackets in ALLOWED_ORIGINS, spaces in values).

Usage:
  source <(python scripts/linux/emit_api_env_exports.py /etc/mana-guruji/api.env)
"""
from __future__ import annotations

import shlex
import sys
from pathlib import Path

from dotenv import dotenv_values


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "/etc/mana-guruji/api.env")
    if not path.is_file():
        print(f"# emit_api_env_exports: missing {path}", file=sys.stderr)
        return 1
    for key, val in dotenv_values(path).items():
        if not key:
            continue
        if val is None:
            print(f"export {key}=")
        else:
            print(f"export {key}={shlex.quote(val)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())