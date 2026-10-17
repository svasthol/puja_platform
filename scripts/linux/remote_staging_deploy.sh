#!/usr/bin/env bash
# Runs ON stg-aio-1 — invoked by GitHub Actions deploy-staging or manual opc user.
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-/opt/mana-guruji/src/puja_platform}"
VENV_DIR="${VENV_DIR:-/opt/mana-guruji/venv}"
GIT_REF="${GIT_REF:-origin/dev}"
RUN_PYTHON_BOOTSTRAP="${RUN_PYTHON_BOOTSTRAP:-1}"
RUN_DATA_SERVICES="${RUN_DATA_SERVICES:-0}"
RUN_DB_BOOTSTRAP="${RUN_DB_BOOTSTRAP:-0}"
RUN_MIGRATE="${RUN_MIGRATE:-1}"
RESTART_SERVICES="${RESTART_SERVICES:-1}"

log() { echo "[remote_staging_deploy] $*"; }

cd "$REPO_ROOT"

log "git fetch + checkout ${GIT_REF}"
git fetch origin
if git show-ref --verify --quiet "refs/remotes/${GIT_REF}"; then
  git checkout -B deploy-staging "${GIT_REF}"
  git reset --hard "${GIT_REF}"
else
  git pull --ff-only origin "$(echo "$GIT_REF" | sed 's|origin/||')"
fi

chmod +x scripts/linux/*.sh scripts/migrate.sh scripts/bootstrap.sh 2>/dev/null || true

if [[ "$RUN_DATA_SERVICES" == "1" ]]; then
  export SKIP_REDIS="${SKIP_REDIS:-0}"
  ./scripts/linux/install_data_services_ol9.sh
fi

if [[ "$RUN_PYTHON_BOOTSTRAP" == "1" ]]; then
  export VENV_DIR INSTALL_SYSTEM=0
  ./scripts/linux/bootstrap_python_runtime.sh
fi

if [[ "$RUN_DB_BOOTSTRAP" == "1" ]]; then
  if [[ ! -f /etc/mana-guruji/api.env ]]; then
    log "ERROR: /etc/mana-guruji/api.env missing — copy deploy/env/staging.api.env.example"
    exit 1
  fi
  set -a
  # shellcheck source=/dev/null
  source /etc/mana-guruji/api.env
  set +a
  export DATABASE_URL="${DATABASE_ADMIN_URL}"
  ./scripts/bootstrap.sh
fi

if [[ "$RUN_MIGRATE" == "1" ]]; then
  if [[ ! -f /etc/mana-guruji/api.env ]]; then
    log "SKIP migrate: /etc/mana-guruji/api.env missing — copy deploy/env/staging.api.env.example, then re-run with run_migrate"
  else
    export VENV_DIR
    ./scripts/migrate.sh
  fi
fi

if [[ "$RESTART_SERVICES" == "1" ]]; then
  if systemctl list-unit-files | grep -q mana-guruji-api.service; then
    sudo systemctl restart mana-guruji-api mana-guruji-celery-worker mana-guruji-celery-beat
  else
    log "systemd units not installed — run deploy/staging/install_systemd.sh once"
  fi
fi

log "Done."
