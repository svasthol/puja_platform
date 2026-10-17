#!/usr/bin/env bash
# PGDG yum repos on Oracle Linux 9 aarch64: default .repo files break dnf (404 on pgdg-common/pgdg18).
set -euo pipefail

PGDG_OL9_REPOS=(pgdg16-ol9-aarch64 pgdg-common-ol9-aarch64 pgdg-extras-ol9-aarch64)

pgdg_fixup_ol9_aarch64() {
  [[ "$(uname -m)" == "aarch64" ]] || return 0
  [[ -f /etc/oracle-release ]] || grep -qi 'oracle linux' /etc/os-release 2>/dev/null || return 0

  if ls /etc/yum.repos.d/pgdg*.repo >/dev/null 2>&1; then
    while IFS= read -r repo; do
      [[ -n "$repo" ]] && sudo dnf -qy config-manager --disable "$repo" 2>/dev/null || true
    done < <(grep -hoP '^\[\K[^\]]+' /etc/yum.repos.d/pgdg*.repo 2>/dev/null | sort -u)
  fi

  sudo tee /etc/yum.repos.d/pgdg-ol9-aarch64-pinned.repo >/dev/null <<'EOF'
[pgdg16-ol9-aarch64]
name=PostgreSQL 16 OL9 aarch64 (PGDG)
baseurl=https://download.postgresql.org/pub/repos/yum/16/redhat/rhel-9-aarch64
enabled=1
gpgcheck=1
gpgkey=https://download.postgresql.org/pub/repos/yum/RPM-GPG-KEY-PGDG

[pgdg-common-ol9-aarch64]
name=PostgreSQL common OL9 aarch64 (PGDG)
baseurl=https://download.postgresql.org/pub/repos/yum/common/redhat/rhel-9-aarch64
enabled=1
gpgcheck=1
gpgkey=https://download.postgresql.org/pub/repos/yum/RPM-GPG-KEY-PGDG

[pgdg-extras-ol9-aarch64]
name=PostgreSQL extras OL9 aarch64 (PGDG) — GDAL/GEOS/PROJ for PostGIS
baseurl=https://download.postgresql.org/pub/repos/yum/extras/redhat/rhel-9-aarch64
enabled=1
gpgcheck=1
gpgkey=https://download.postgresql.org/pub/repos/yum/RPM-GPG-KEY-PGDG
EOF

  sudo dnf clean metadata -y 2>/dev/null || true
}

pgdg_enable_flags() {
  local flags=""
  for r in "${PGDG_OL9_REPOS[@]}"; do
    flags+=" --enablerepo=${r}"
  done
  printf '%s' "$flags"
}

pgdg_disable_for_dnf_extras() {
  echo "--disablerepo=pgdg* --disablerepo=pgdg16-ol9-aarch64 --disablerepo=pgdg-common-ol9-aarch64 --disablerepo=pgdg-extras-ol9-aarch64"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  pgdg_fixup_ol9_aarch64
  echo "pgdg_ol9_fixup: OK"
fi
