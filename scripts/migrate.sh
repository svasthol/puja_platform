#!/usr/bin/env bash
# Apply full migration chain + grants (every staging/prod deploy).
# Requires: venv active OR VENV_DIR; env from /etc/mana-guruji/api.env
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

VENV_DIR="${VENV_DIR:-${REPO_ROOT}/.venv}"
export REPO_ROOT VENV_DIR

ENV_FILE="${ENV_FILE:-/etc/mana-guruji/api.env}"
if [[ -f "$ENV_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$SCRIPT_DIR/linux/source_api_env.sh" "$ENV_FILE"
fi
if [[ -f "${VENV_DIR}/bin/activate" ]]; then
  # shellcheck source=/dev/null
  source "${VENV_DIR}/bin/activate"
fi

MIGRATE_URL="${DATABASE_MIGRATE_URL:-${DATABASE_ADMIN_URL:-}}"
if [[ -z "$MIGRATE_URL" ]]; then
  echo "migrate.sh: set DATABASE_MIGRATE_URL or DATABASE_ADMIN_URL in ${ENV_FILE}"
  exit 1
fi

ADMIN_URL="${DATABASE_ADMIN_URL:-$MIGRATE_URL}"

export DATABASE_URL="$MIGRATE_URL"
echo "migrate.sh: alembic upgrade head"
alembic upgrade head

echo "migrate.sh: run_sql_migrations.py (manifest — all apply_migration_*.py)"
python scripts/run_sql_migrations.py

export DATABASE_URL="$ADMIN_URL"
echo "migrate.sh: apply_grants.py"
python scripts/apply_grants.py

echo "migrate.sh: OK"
