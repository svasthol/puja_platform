#!/usr/bin/env bash
# One-time (idempotent): PostgreSQL 16 + PostGIS + Redis on Oracle Linux 9 — stg-aio-1.
set -euo pipefail

MARKER="/var/lib/mana-guruji/data_services_installed"
DB_NAME="${DB_NAME:-Mana_Guruji}"
SKIP_REDIS="${SKIP_REDIS:-0}"

if [[ "$(id -u)" -eq 0 ]]; then
  echo "Run as opc with sudo, not root."
  exit 1
fi

if [[ -f "$MARKER" ]]; then
  echo "Data services already installed ($MARKER). Skipping."
  exit 0
fi

echo "[install_data_services] PGDG + PostgreSQL 16 + PostGIS + Redis"
ARCH="$(uname -m)"
sudo dnf install -y "https://download.postgresql.org/pub/repos/yum/reporpms/EL-9-${ARCH}/pgdg-redhat-repo-latest.noarch.rpm"
sudo dnf -qy module disable postgresql || true
if [[ "$SKIP_REDIS" == "1" ]]; then
  sudo dnf install -y postgresql16-server postgresql16-contrib postgis34_16
else
  sudo dnf install -y postgresql16-server postgresql16-contrib postgis34_16 redis
fi

if [[ ! -d /var/lib/pgsql/16/data/base ]]; then
  sudo /usr/pgsql-16/bin/postgresql-16-setup initdb
fi

sudo systemctl enable --now postgresql-16
if [[ "$SKIP_REDIS" != "1" ]]; then
  sudo systemctl enable --now redis
fi

echo "[install_data_services] Create database ${DB_NAME}"
sudo -u postgres /usr/pgsql-16/bin/psql -tc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1 \
  || sudo -u postgres /usr/pgsql-16/bin/createdb "${DB_NAME}"

echo "[install_data_services] Extensions (superuser)"
sudo -u postgres /usr/pgsql-16/bin/psql -d "${DB_NAME}" -c "CREATE EXTENSION IF NOT EXISTS postgis;"
sudo -u postgres /usr/pgsql-16/bin/psql -d "${DB_NAME}" -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"
sudo -u postgres /usr/pgsql-16/bin/psql -d "${DB_NAME}" -c "CREATE EXTENSION IF NOT EXISTS btree_gist;"

sudo mkdir -p /var/lib/mana-guruji
sudo touch "$MARKER"
sudo chown opc:opc "$MARKER"
echo "install_data_services_ol9: OK"
