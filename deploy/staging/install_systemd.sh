#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
sudo mkdir -p /etc/mana-guruji
if [[ ! -f /etc/mana-guruji/api.env ]]; then
  echo "Copy ${REPO_ROOT}/deploy/env/staging.api.env.example to /etc/mana-guruji/api.env and edit."
  sudo cp "${REPO_ROOT}/deploy/env/staging.api.env.example" /etc/mana-guruji/api.env
  sudo chmod 600 /etc/mana-guruji/api.env
fi
for u in mana-guruji-api mana-guruji-celery-worker mana-guruji-celery-beat mana-guruji-admin; do
  sudo cp "${REPO_ROOT}/deploy/systemd/${u}.service" "/etc/systemd/system/${u}.service"
done
sudo systemctl daemon-reload
sudo systemctl enable mana-guruji-api mana-guruji-celery-worker mana-guruji-celery-beat
echo "install_systemd: OK — does NOT create OCI VMs, Docker, or Redis (use Deploy Redis staging + api.env REDIS_URL)."
echo "install_systemd: API + Celery units enabled. Admin unit copied; enable/start after: ./deploy/staging/install_admin.sh"
