#!/usr/bin/env bash
# Idempotent Node.js 22 LTS on Oracle Linux 9 (aarch64/x86_64) — for admin_ui on stg-aio-1.
set -euo pipefail

MARKER="/var/lib/mana-guruji/node_22_installed"
NODE_MAJOR="${NODE_MAJOR:-22}"

need_version() {
  command -v node >/dev/null 2>&1 || return 1
  local v
  v="$(node -p "process.versions.node.split('.')[0]" 2>/dev/null || echo 0)"
  [[ "$v" == "$NODE_MAJOR" ]]
}

if [[ -f "$MARKER" ]] && need_version; then
  echo "[ensure_node_ol9] Node $(node -v) OK ($MARKER)"
  exit 0
fi

if [[ "$(id -u)" -eq 0 ]]; then
  echo "Run as opc with sudo, not root."
  exit 1
fi

echo "[ensure_node_ol9] Installing Node.js ${NODE_MAJOR}.x (NodeSource)"
sudo mkdir -p /var/lib/mana-guruji
curl -fsSL "https://rpm.nodesource.com/setup_${NODE_MAJOR}.x" | sudo bash -
sudo dnf install -y nodejs
node -v
npm -v
sudo touch "$MARKER"
