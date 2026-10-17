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
# shellcheck source=pgdg_ol9_fixup.sh
source "$(dirname "${BASH_SOURCE[0]}")/pgdg_ol9_fixup.sh"
if ! ls /etc/yum.repos.d/pgdg*.repo >/dev/null 2>&1; then
  sudo dnf install -y "https://download.postgresql.org/pub/repos/yum/reporpms/EL-9-${ARCH}/pgdg-redhat-repo-latest.noarch.rpm"
fi
pgdg_fixup_ol9_aarch64
PGDG_ENABLE="$(pgdg_enable_flags)"
sudo dnf -qy module disable postgresql || true
# CodeReady Builder often required for GDAL/GEOS build deps on OL9.
sudo dnf install -y oraclelinux-developer-release-el9 2>/dev/null || true
sudo dnf config-manager --enable ol9_codeready_builder 2>/dev/null || true
if [[ "$SKIP_REDIS" == "1" ]]; then
  sudo dnf install -y --disablerepo='pgdg*' ${PGDG_ENABLE} \
    postgresql16-server postgresql16-contrib postgis34_16
else
  sudo dnf install -y --disablerepo='pgdg*' ${PGDG_ENABLE} \
    postgresql16-server postgresql16-contrib postgis34_16
  sudo dnf install -y redis
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
