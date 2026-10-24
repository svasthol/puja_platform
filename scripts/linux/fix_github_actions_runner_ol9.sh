#!/usr/bin/env bash
# Repair GitHub Actions self-hosted runner on OL9 (stg-aio-1). Run as opc from actions-runner dir.
set -euo pipefail

RUNNER_ROOT="${RUNNER_ROOT:-${HOME}/actions-runner}"

log() { echo "[fix_github_actions_runner] $*"; }

if [[ "$(id -u)" -eq 0 ]]; then
  log "Run as opc, not root."
  exit 1
fi

if [[ ! -d "${RUNNER_ROOT}" ]]; then
  log "Missing ${RUNNER_ROOT} — install runner from GitHub Settings → Actions → Runners first."
  exit 1
fi

cd "${RUNNER_ROOT}"

ARCH="$(uname -m)"
if [[ "${ARCH}" != "aarch64" ]]; then
  log "WARN: expected aarch64 for stg-aio-1, got ${ARCH}"
fi

if [[ -f bin/Runner.Listener ]]; then
  LISTENER_ARCH="$(file -b bin/Runner.Listener | grep -oE 'ARM aarch64|x86-64' || true)"
  if [[ "${LISTENER_ARCH}" == *x86* ]]; then
    log "ERROR: Runner.Listener is x86-64 — download linux-arm64 package from GitHub."
    exit 1
  fi
fi

log "Fix ownership and execute bits"
sudo chown -R opc:opc "${RUNNER_ROOT}"
chmod u+rx "${HOME}" 2>/dev/null || true
chmod -R u+rwX,go-rwx "${RUNNER_ROOT}"
chmod +x runsvc.sh config.sh svc.sh 2>/dev/null || true
[[ -f bin/Runner.Listener ]] && chmod +x bin/Runner.Listener

if command -v dos2unix >/dev/null 2>&1; then
  dos2unix runsvc.sh config.sh svc.sh 2>/dev/null || true
fi

if [[ -f runsvc.sh ]] && ! head -1 runsvc.sh | grep -q '^#!'; then
  log "WARN: runsvc.sh missing shebang — re-extract runner tarball."
fi

log "SELinux: restore contexts (if enabled)"
if command -v getenforce >/dev/null 2>&1 && [[ "$(getenforce)" != "Disabled" ]]; then
  sudo restorecon -Rv "${RUNNER_ROOT}" || true
fi

log "Stop and remove old systemd units"
if [[ -x ./svc.sh ]]; then
  sudo ./svc.sh stop 2>/dev/null || true
  sudo ./svc.sh uninstall 2>/dev/null || true
fi
sudo rm -f /etc/systemd/system/actions.runner.*.service
sudo systemctl daemon-reload

log "Sanity: opc can execute runsvc.sh"
if ! test -x runsvc.sh; then
  log "ERROR: runsvc.sh not executable"
  exit 1
fi
if ! bash -n runsvc.sh 2>/dev/null; then
  log "WARN: bash -n runsvc.sh reported syntax issues"
fi

log "Re-install service (user opc)"
sudo ./svc.sh install opc
sudo ./svc.sh start
sleep 2
sudo ./svc.sh status || true

log "Recent journal:"
sudo journalctl -u 'actions.runner.*' -n 20 --no-pager || true

log "Done. Confirm runner Idle in GitHub → Settings → Actions → Runners."
