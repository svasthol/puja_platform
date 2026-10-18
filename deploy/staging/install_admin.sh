#!/usr/bin/env bash
# Model 2: build admin_ui on stg-aio-1 and install mana-guruji-admin.service.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ADMIN_ENV="/etc/mana-guruji/admin.env"
UNITS_ONLY="${UNITS_ONLY:-0}"

if [[ "$(id -u)" -eq 0 ]]; then
  echo "Run as opc with sudo, not root."
  exit 1
fi

install_unit() {
  sudo cp "${REPO_ROOT}/deploy/systemd/mana-guruji-admin.service" /etc/systemd/system/mana-guruji-admin.service
  sudo systemctl daemon-reload
  sudo systemctl enable mana-guruji-admin
}

if [[ "$UNITS_ONLY" == "1" ]]; then
  install_unit
  echo "install_admin: systemd unit only — run with UNITS_ONLY=0 to build and start."
  exit 0
fi

chmod +x "${REPO_ROOT}/scripts/linux/ensure_node_ol9.sh"
"${REPO_ROOT}/scripts/linux/ensure_node_ol9.sh"

sudo mkdir -p /etc/mana-guruji
if [[ ! -f "$ADMIN_ENV" ]]; then
  echo "Creating ${ADMIN_ENV} from example — edit NEXT_PUBLIC_API_URL if needed, then re-run."
  sudo cp "${REPO_ROOT}/deploy/env/staging.admin.env.example" "$ADMIN_ENV"
  sudo chown root:opc "$ADMIN_ENV"
  sudo chmod 640 "$ADMIN_ENV"
fi

if ! sudo test -r "$ADMIN_ENV"; then
  echo "ERROR: opc cannot read ${ADMIN_ENV} — use: sudo chown root:opc ${ADMIN_ENV} && sudo chmod 640 ${ADMIN_ENV}"
  exit 1
fi

echo "install_admin: npm ci + build (NEXT_PUBLIC_* from ${ADMIN_ENV})"
cd "${REPO_ROOT}/admin_ui"

# Do not source NODE_ENV=production before npm ci — npm omits devDependencies (tailwind, postcss, tsc).
NEXT_PUBLIC_API_URL="$(grep -E '^[[:space:]]*NEXT_PUBLIC_API_URL=' "$ADMIN_ENV" | tail -1 | cut -d= -f2- | tr -d '[:space:]')"
if [[ -z "${NEXT_PUBLIC_API_URL}" ]]; then
  echo "ERROR: NEXT_PUBLIC_API_URL unset in ${ADMIN_ENV}"
  exit 1
fi
export NEXT_PUBLIC_API_URL
unset NODE_ENV

npm ci
npm run build

install_unit
sudo systemctl restart mana-guruji-admin
echo "install_admin: OK — Admin on :3000 (e.g. http://140.245.245.201:3000); restrict OCI ingress to ops /32"
echo "install_admin: ensure api.env ALLOWED_ORIGINS includes your admin origin (e.g. http://140.245.245.201:3000)"
