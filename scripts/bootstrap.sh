#!/usr/bin/env bash
# One-time database bootstrap (superuser DATABASE_URL). Not run on every deploy.
# Per-deploy: migrate as puja_migrate + python scripts/apply_grants.py
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

python scripts/bootstrap_puja_app_role.py
python scripts/bootstrap_puja_migrate_role.py

echo "bootstrap.sh: OK (puja_app + puja_migrate roles)"
