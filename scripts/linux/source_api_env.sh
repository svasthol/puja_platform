#!/usr/bin/env bash
# Load /etc/mana-guruji/api.env without bash parsing JSON or spaces in values.
set -euo pipefail

ENV_FILE="${1:-/etc/mana-guruji/api.env}"
VENV_DIR="${VENV_DIR:-}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "source_api_env: file not found: ${ENV_FILE}" >&2
  return 1 2>/dev/null || exit 1
fi

_emit() {
  if [[ -n "$VENV_DIR" && -x "${VENV_DIR}/bin/python" ]]; then
    "${VENV_DIR}/bin/python" "${REPO_ROOT:-.}/scripts/linux/emit_api_env_exports.py" "$ENV_FILE"
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    python3 "${SCRIPT_DIR}/emit_api_env_exports.py" "$ENV_FILE"
    return
  fi
  echo "source_api_env: need VENV_DIR python or python3" >&2
  return 1 2>/dev/null || exit 1
}

set -a
# shellcheck source=/dev/null
source <(_emit)
set +a