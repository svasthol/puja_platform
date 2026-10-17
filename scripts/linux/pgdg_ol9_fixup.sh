#!/usr/bin/env bash
# PGDG yum repos on Oracle Linux 9 aarch64: default .repo files break dnf (404 on pgdg-common/pgdg18).
set -euo pipefail

pgdg_fixup_ol9_aarch64() {
  [[ "$(uname -m)" == "aarch64" ]] || return 0
  [[ -f /etc/oracle-release ]] || grep -qi 'oracle linux' /etc/os-release 2>/dev/null || return 0

  if ls /etc/yum.repos.d/pgdg*.repo >/dev/null 2>&1; then
    # Disable every PGDG repo shipped by pgdg-redhat-repo (broken $releasever on OL).
    while IFS= read -r repo; do
      [[ -n "$repo" ]] && sudo dnf -qy config-manager --disable "$repo" 2>/dev/null || true
    done < <(grep -hoP '^\[\K[^\]]+' /etc/yum.repos.d/pgdg*.repo 2>/dev/null | sort -u)
  fi

  # Single pinned repo for PostgreSQL 16 + PostGIS RPMs on RHEL9-compatible OL9 aarch64.
  sudo tee /etc/yum.repos.d/pgdg16-ol9-aarch64.repo >/dev/null <<'EOF'
[pgdg16-ol9-aarch64]
name=PostgreSQL 16 OL9 aarch64 (PGDG)
baseurl=https://download.postgresql.org/pub/repos/yum/16/redhat/rhel-9-aarch64
enabled=1
gpgcheck=1
gpgkey=https://download.postgresql.org/pub/repos/yum/RPM-GPG-KEY-PGDG
EOF

  sudo dnf clean metadata -y 2>/dev/null || true
}

pgdg_disable_for_dnf_extras() {
  # Bootstrap OS packages use Oracle Linux repos only.
  echo "--disablerepo=pgdg* --disablerepo=pgdg16-ol9-aarch64"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  pgdg_fixup_ol9_aarch64
  echo "pgdg_ol9_fixup: OK"
fi
