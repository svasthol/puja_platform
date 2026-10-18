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
RUN_SYSTEMD_INSTALL="${RUN_SYSTEMD_INSTALL:-0}"
RUN_ADMIN_DEPLOY="${RUN_ADMIN_DEPLOY:-0}"
RESTART_SERVICES="${RESTART_SERVICES:-1}"
DEPLOY_COMPONENT="${DEPLOY_COMPONENT:-full}"

log() { echo "[remote_staging_deploy] $*"; }

case "$DEPLOY_COMPONENT" in
  full)
    RUN_ADMIN_DEPLOY=1
    ;;
  admin_only)
    RUN_DATA_SERVICES=0 RUN_DB_BOOTSTRAP=0 RUN_MIGRATE=0 RUN_PYTHON_BOOTSTRAP=0 RUN_SYSTEMD_INSTALL=0
    RESTART_SERVICES=0 RUN_ADMIN_DEPLOY=1 ADMIN_FORCE_INSTALL=1
    ;;
  backend_only)
    RUN_DATA_SERVICES=0 RUN_DB_BOOTSTRAP=0 RUN_MIGRATE=0 RUN_PYTHON_BOOTSTRAP=1 RUN_SYSTEMD_INSTALL=0
    ;;
  db_migrate_only)
    RUN_DATA_SERVICES=0 RUN_DB_BOOTSTRAP=0 RUN_MIGRATE=1 RUN_PYTHON_BOOTSTRAP=0 RUN_SYSTEMD_INSTALL=0 RESTART_SERVICES=0
    ;;
  db_bootstrap_only)
    RUN_DATA_SERVICES=0 RUN_DB_BOOTSTRAP=1 RUN_MIGRATE=0 RUN_PYTHON_BOOTSTRAP=0 RUN_SYSTEMD_INSTALL=0 RESTART_SERVICES=0
    ;;
  data_services_only)
    RUN_DATA_SERVICES=1 RUN_DB_BOOTSTRAP=0 RUN_MIGRATE=0 RUN_PYTHON_BOOTSTRAP=0 RUN_SYSTEMD_INSTALL=0 RESTART_SERVICES=0
    ;;
  install_systemd)
    RUN_DATA_SERVICES=0 RUN_DB_BOOTSTRAP=0 RUN_MIGRATE=0 RUN_PYTHON_BOOTSTRAP=0 RUN_SYSTEMD_INSTALL=1 RESTART_SERVICES=1
    ;;
  *)
    log "ERROR: unknown DEPLOY_COMPONENT=${DEPLOY_COMPONENT}"
    exit 1
    ;;
esac

cd "$REPO_ROOT"

log "git fetch + sync ${GIT_REF} (staging VM must match origin; local edits discarded)"
git fetch origin
if git show-ref --verify --quiet "refs/remotes/${GIT_REF}"; then
  # -f: do not fail when opc left hotfix edits on the clone (common on self-hosted runner).
  git checkout -f -B deploy-staging "${GIT_REF}"
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

if [[ "$RUN_SYSTEMD_INSTALL" == "1" ]]; then
  chmod +x deploy/staging/install_systemd.sh 2>/dev/null || true
  ./deploy/staging/install_systemd.sh
  chmod +x deploy/staging/install_admin.sh 2>/dev/null || true
  UNITS_ONLY=1 ./deploy/staging/install_admin.sh || true
fi

if [[ "$RUN_ADMIN_DEPLOY" == "1" ]]; then
  chmod +x deploy/staging/install_admin.sh scripts/linux/ensure_node_ol9.sh 2>/dev/null || true
  if [[ -f /etc/mana-guruji/admin.env ]] || [[ "${ADMIN_FORCE_INSTALL:-0}" == "1" ]]; then
    ./deploy/staging/install_admin.sh
  else
    log "SKIP admin: no /etc/mana-guruji/admin.env — one-time: ./deploy/staging/install_admin.sh (STAGING_ADMIN_UI.md)"
  fi
fi

if [[ "${RUN_REDIS_ENSURE:-0}" == "1" ]]; then
  if [[ -f /etc/mana-guruji/api.env ]]; then
    set -a
    # shellcheck source=/dev/null
    source /etc/mana-guruji/api.env
    set +a
    export VENV_DIR
    "${VENV_DIR}/bin/python" scripts/ensure_redis_logical_dbs.py --strict || log "WARN: redis ensure failed"
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
