#!/usr/bin/env bash
# Apply full migration chain + grants (every staging/prod deploy).
# Requires: venv active OR VENV_DIR; env from /etc/mana-guruji/api.env
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

ENV_FILE="${ENV_FILE:-/etc/mana-guruji/api.env}"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$ENV_FILE"
  set +a
fi

VENV_DIR="${VENV_DIR:-${REPO_ROOT}/.venv}"
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

for n in 012 013 014 015 016 017 018 019 020 021 022 023 024 025 026 027; do
  echo "migrate.sh: apply_migration_${n}.py"
  python "scripts/apply_migration_${n}.py"
done

echo "migrate.sh: apply_migrations_028_032.py"
python scripts/apply_migrations_028_032.py

export DATABASE_URL="$ADMIN_URL"
echo "migrate.sh: apply_grants.py"
python scripts/apply_grants.py

echo "migrate.sh: OK"
