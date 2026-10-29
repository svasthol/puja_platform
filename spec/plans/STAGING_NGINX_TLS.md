# Staging nginx + TLS (`managuruji.in`)

**Host:** `stg-aio-1` · **DNS (Wix):**

| Hostname | A record |
|----------|----------|
| `api-stg.managuruji.in` | `140.245.245.201` |
| `admin-stg.managuruji.in` | `140.245.245.201` |

**Prod:** OCI NLB TLS — **no nginx on app nodes** ([`STAGING_CONFIG_ROLLOUT.md`](./STAGING_CONFIG_ROLLOUT.md) edge policy).

---

## Install (manual on VM)

After `git pull` on `dev`:

```bash
cd /opt/mana-guruji/src/puja_platform   # or your REPO_ROOT
chmod +x deploy/staging/install_nginx_tls.sh
CERTBOT_EMAIL=you@example.com sudo -E ./deploy/staging/install_nginx_tls.sh
```

---

## GitHub Actions

1. Repo **Settings → Secrets and variables → Actions → Environment `staging`**
2. Add secret **`STAGING_CERTBOT_EMAIL`** (Let's Encrypt account email)
3. **Actions → Deploy staging → Run workflow**
   - Branch: `dev`
   - Component: **`nginx_tls`**

Does **not** run migrate or restart API unless you run `full` / `backend_only` separately.

---

## After HTTPS works

1. `/etc/mana-guruji/api.env`:
   - `KYC_REDIRECT_URL=https://api-stg.managuruji.in/v1/pujari/kyc/callback`
   - `ALLOWED_ORIGINS` includes `https://admin-stg.managuruji.in`
2. `/etc/mana-guruji/admin.env`: `NEXT_PUBLIC_API_URL=https://api-stg.managuruji.in` → `./deploy/staging/install_admin.sh`
3. `sudo systemctl restart mana-guruji-api mana-guruji-celery-worker mana-guruji-celery-beat`
4. Register Setu callback URL (exact match)
5. Flutter: `--dart-define=API_BASE_URL=https://api-stg.managuruji.in`

Optional: remove public **8000** from OCI security list once all clients use HTTPS.

---

## Files

| Path | Role |
|------|------|
| [`deploy/nginx/mana-guruji-staging-api.conf`](../../deploy/nginx/mana-guruji-staging-api.conf) | API reverse proxy |
| [`deploy/nginx/mana-guruji-staging-admin.conf`](../../deploy/nginx/mana-guruji-staging-admin.conf) | Admin → `:3000` |
| [`deploy/staging/install_nginx_tls.sh`](../../deploy/staging/install_nginx_tls.sh) | dnf + firewalld + certbot |
