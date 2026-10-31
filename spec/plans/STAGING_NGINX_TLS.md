# Staging nginx + TLS (`managuruji.in`)

**Host:** `stg-aio-1` · **DNS (Wix):**

| Hostname | A record |
|----------|----------|
| `api-stg.managuruji.in` | `140.245.245.201` |
| `admin-stg.managuruji.in` | `140.245.245.201` |

**Prod:** OCI NLB TLS — **no nginx on app nodes** ([`STAGING_CONFIG_ROLLOUT.md`](./STAGING_CONFIG_ROLLOUT.md) edge policy).

---

## Which email for `STAGING_CERTBOT_EMAIL`?

**You do not get this from Wix.** SSL on `managuruji.in` at Wix is a separate product (Wix’s Let’s Encrypt account on Wix servers). Staging certs on **`stg-aio-1`** are a **new** Let’s Encrypt account on **your VM** — Wix does not expose that contact address.

**Use any inbox you control** (personal Gmail, work email, etc.). It does **not** need to be `@managuruji.in`. Let’s Encrypt only uses it for:

- agreeing to terms when creating the ACME account  
- optional expiry / policy notices (not shown on the certificate)

Pick one address your team monitors and set GitHub secret **`STAGING_CERTBOT_EMAIL`** to that same value.

**If certbot already ran on the VM**, the account email may already be on disk:

```bash
sudo grep -r '"mailto:' /etc/letsencrypt/accounts/ 2>/dev/null | head -1
# or: sudo certbot show_account --account $(sudo ls /etc/letsencrypt/accounts/acme-v02.api.letsencrypt.org/directory/)
```

**If you truly have no mailbox to use:** certbot allows `--register-unsafely-without-email` (not recommended). Our install script requires `CERTBOT_EMAIL` for automation — use a real address when possible.

---

## Certbot `connection` / firewall timeout

**Symptom:** *Timeout during connect (likely firewall problem)* on `http://…/.well-known/acme-challenge/…`.

**Cause:** **firewalld** on the VM can allow 80/443 while the **OCI security list** still only allows your laptop `/32` on **8000/3000** (`STG-S5b`). Let's Encrypt must reach **TCP 80** from the public internet (HTTP-01). After the cert, clients need **443** too.

**Fix (OCI Console — fastest):**

1. **Networking → VCN** → staging VCN → **Security Lists** → list on the public subnet (e.g. `mana-guruji-stg-ssh`).
2. Add ingress: source **`0.0.0.0/0`**, TCP **80** and **443**.
3. From your laptop: `curl -v --connect-timeout 5 http://api-stg.managuruji.in/` — must **connect** (404/502 is fine; *timeout* = OCI still blocking).
4. On the VM (nginx already installed; LE account already registered):

```bash
sudo certbot --nginx --non-interactive --agree-tos --no-eff-email \
  -m you@example.com \
  -d api-stg.managuruji.in -d admin-stg.managuruji.in --redirect
sudo systemctl enable --now certbot-renew.timer
```

**Fix (Terraform):** `modules/staging_stack` — `public_web_tcp_ports` / `public_web_allowed_cidrs`; `terraform apply` in `infra/oci/terraform/environments/staging`.

---

## 502 + `connect() … (13: Permission denied)` to `:8000` / `:3000`

**Not** file permissions. On **OL9**, nginx (SELinux **`httpd_t`**) cannot open TCP to uvicorn/Next.js until **`httpd_can_network_connect`** is enabled. TLS/nginx are fine; proxied requests return **502**.

```bash
sudo setsebool -P httpd_can_network_connect 1
curl -sS http://127.0.0.1:8000/health/live
curl -sS https://api-stg.managuruji.in/health/live
```

Ensure backends are up: `sudo systemctl status mana-guruji-api` and admin on `:3000` (`ss -tlnp | grep -E ':8000|:3000'`).

Log lines probing `/.env`, `wp-config.php`, etc. are **public scanners** — expected once 80/443 are open.

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
