#!/usr/bin/env bash
# Idempotent: OL9+ Linux Python 3.12 venv + requirements.txt (staging/prod).
# Same script for stg-aio-1 and future app nodes. Dev on Windows uses uv locally — see CURSOR_SETUP.md.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV_DIR="${VENV_DIR:-${REPO_ROOT}/.venv}"
PYTHON="${PYTHON:-python3.12}"
REQUIREMENTS="${REQUIREMENTS:-${REPO_ROOT}/requirements.txt}"
OS_PACKAGES="${OS_PACKAGES:-${REPO_ROOT}/scripts/linux/os-packages.ol9.txt}"
INSTALL_SYSTEM="${INSTALL_SYSTEM:-1}"

log() { echo "[bootstrap_python_runtime] $*"; }

if [[ "$(id -u)" -eq 0 ]]; then
  log "Run as opc (or deploy user), not root — script uses sudo for dnf only."
  exit 1
fi

if [[ "${INSTALL_SYSTEM}" == "1" ]]; then
  if [[ -f /etc/oracle-release ]] || grep -qi 'oracle linux' /etc/os-release 2>/dev/null; then
    log "Installing OS packages from ${OS_PACKAGES}"
    # shellcheck disable=SC2046
    sudo dnf -y install $(grep -v '^#' "${OS_PACKAGES}" | grep -v '^[[:space:]]*$' | tr '\n' ' ')
  else
    log "Non-OL9 host — skip dnf (set INSTALL_SYSTEM=0 to silence)"
  fi
fi

if ! command -v "${PYTHON}" >/dev/null 2>&1; then
  log "Missing ${PYTHON}. On OL9: sudo dnf install python3.12 python3.12-devel"
  exit 1
fi

"${PYTHON}" -c 'import sys; assert sys.version_info[:2] == (3, 12), sys.version'

if [[ ! -d "${VENV_DIR}" ]]; then
  log "Creating venv at ${VENV_DIR}"
  "${PYTHON}" -m venv "${VENV_DIR}"
fi

# shellcheck source=/dev/null
source "${VENV_DIR}/bin/activate"
python -m pip install -U pip wheel
python -m pip install -r "${REQUIREMENTS}"
# requirements.txt is compiled without [standard] extras markers — align with pyproject.toml
python -m pip install 'uvicorn[standard]==0.34.0'

log "Running verify_linux_runtime.py"
python "${REPO_ROOT}/scripts/verify_linux_runtime.py"

log "Done. Activate: source ${VENV_DIR}/bin/activate"
