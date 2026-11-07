#!/usr/bin/env bash
# Staging TLS edge on stg-aio-1 — nginx + Let's Encrypt (certbot).
# DNS must resolve api-stg / admin-stg → this host before certbot runs.
#
# One-time / repeat (idempotent):
#   CERTBOT_EMAIL=you@example.com sudo -E ./deploy/staging/install_nginx_tls.sh
#
# GitHub Actions: workflow_dispatch component=nginx_tls + secret STAGING_CERTBOT_EMAIL
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
API_HOST="${STAGING_API_HOST:-api-stg.managuruji.in}"
ADMIN_HOST="${STAGING_ADMIN_HOST:-admin-stg.managuruji.in}"
CERTBOT_EMAIL="${CERTBOT_EMAIL:-}"
RUN_CERTBOT="${RUN_CERTBOT:-1}"

log() { echo "[install_nginx_tls] $*"; }

if [[ "$(id -u)" -ne 0 ]] && ! sudo -n true 2>/dev/null; then
  log "Run as root or as opc with passwordless sudo."
fi

SUDO=""
if [[ "$(id -u)" -ne 0 ]]; then
  SUDO="sudo"
fi

log "Installing nginx + certbot (OL9)..."
$SUDO dnf install -y nginx certbot python3-certbot-nginx

log "Installing site configs (${API_HOST}, ${ADMIN_HOST})..."
$SUDO mkdir -p /etc/nginx/conf.d
$SUDO cp "${REPO_ROOT}/deploy/nginx/mana-guruji-staging-api.conf" /etc/nginx/conf.d/
$SUDO cp "${REPO_ROOT}/deploy/nginx/mana-guruji-staging-admin.conf" /etc/nginx/conf.d/

if command -v firewall-cmd >/dev/null 2>&1; then
  log "Opening firewalld http/https..."
  $SUDO firewall-cmd --permanent --add-service=http 2>/dev/null || true
  $SUDO firewall-cmd --permanent --add-service=https 2>/dev/null || true
  $SUDO firewall-cmd --reload 2>/dev/null || true
fi

if command -v getenforce >/dev/null 2>&1 && [[ "$($SUDO getenforce 2>/dev/null || echo Disabled)" != "Disabled" ]]; then
  log "SELinux: enabling httpd_can_network_connect (nginx → :8000 / :3000)..."
  $SUDO setsebool -P httpd_can_network_connect 1
fi

$SUDO nginx -t
$SUDO systemctl enable nginx
$SUDO systemctl restart nginx

if [[ "$RUN_CERTBOT" != "1" ]]; then
  log "RUN_CERTBOT=0 — HTTP only. Set CERTBOT_EMAIL and re-run for HTTPS."
  exit 0
fi

if [[ -z "$CERTBOT_EMAIL" ]]; then
  log "WARN: CERTBOT_EMAIL not set — nginx HTTP is up; certbot skipped."
  log "  export CERTBOT_EMAIL=... && sudo -E ./deploy/staging/install_nginx_tls.sh"
  exit 0
fi

log "Requesting Let's Encrypt certificates..."
if $SUDO certbot certificates 2>/dev/null | grep -q "Certificate Name: ${API_HOST}"; then
  log "Cert exists — running certbot renew (dry-run check)..."
  $SUDO certbot renew --dry-run
else
  $SUDO certbot --nginx --non-interactive --agree-tos --no-eff-email \
    -m "$CERTBOT_EMAIL" \
    -d "$API_HOST" -d "$ADMIN_HOST" \
    --redirect
fi

$SUDO nginx -t
$SUDO systemctl reload nginx

if command -v systemctl >/dev/null 2>&1; then
  log "Enabling certbot renewal timer..."
  $SUDO systemctl enable --now certbot-renew.timer 2>/dev/null || true
fi

log "Verify:"
log "  curl -sS https://${API_HOST}/health/live"
log "  curl -sS -o /dev/null -w '%{http_code}' https://${ADMIN_HOST}/"
log "Set KYC_REDIRECT_URL=https://${API_HOST}/v1/pujari/kyc/callback in /etc/mana-guruji/api.env"
