# Staging deploy pipeline (dev laptop → GitHub → OCI)

**Host:** `stg-aio-1` · **Target branch:** `dev` · **Inventory:** [`OCI_INFRA_STATUS.md`](./OCI_INFRA_STATUS.md)  
**Full developer procedure (dev → stg → main/prod readiness):** [`DEVELOPER_RELEASE_FLOW.md`](./DEVELOPER_RELEASE_FLOW.md)

## Flow

```text
[Laptop]  git push origin dev
    ↓
[GitHub]  ci.yml — linux/arm64 pip + G1/G2 preflight
    ↓
[GitHub]  deploy-staging.yml — SSH to 140.245.245.201
    ↓
[VM]      remote_staging_deploy.sh
            → git pull
            → bootstrap_python_runtime.sh (pip)
            → migrate.sh (DB)
            → systemctl restart api/worker/beat
            → (full) install_admin.sh — Next.js :3000
    ↓
[GitHub]  curl :8000/health/live and :3000 (admin) on VM
```

**Terraform** for staging compute is **already applied** — not part of app deploy. Optional: [`infra-terraform-staging.yml`](../../.github/workflows/infra-terraform-staging.yml) on IaC PRs.

---

## Workflows

| Workflow | Trigger | Role |
|----------|---------|------|
| [`ci.yml`](../../.github/workflows/ci.yml) | push/PR `main`, `dev` | Compile-time: arm64 wheels + import verify |
| [`deploy-staging.yml`](../../.github/workflows/deploy-staging.yml) | push `dev` (app paths) or **manual** | Runtime deploy on VM |
| [`deploy-prod.yml`](../../.github/workflows/deploy-prod.yml) | manual | Prod preflight (rollout TBD) |
| [`db-verify.yml`](../../.github/workflows/db-verify.yml) | manual | Strict `spec/db` vs live DB on staging; optional dev compare |
| [`db-dev-staging-parity.yml`](../../.github/workflows/db-dev-staging-parity.yml) | manual | Developer `/32` ingress + deep catalog compare + safe `migrate.sh` |
| [`deploy-redis-staging.yml`](../../.github/workflows/deploy-redis-staging.yml) | manual | Terraform E2 Micro + Redis Docker |
| [`redis-ensure-staging.yml`](../../.github/workflows/redis-ensure-staging.yml) | manual | PING/bootstrap logical Redis DB 0,1,2 from `api.env` |
| [`staging-storage-smoke.yml`](../../.github/workflows/staging-storage-smoke.yml) | manual | OCI/S3 catalog + KYC — [`STAGING_CONFIG_ROLLOUT.md`](./STAGING_CONFIG_ROLLOUT.md) |

---

## Manual deploy — pick branch + component

**Actions → Deploy staging → Run workflow**

| `component` | Does |
|-------------|------|
| `full` | git pull, pip, migrate, restart API/worker/beat, **rebuild admin** (see [`STAGING_ADMIN_UI.md`](./STAGING_ADMIN_UI.md)) |
| `admin_only` | git pull + `install_admin.sh` only |
| `backend_only` | pip + restart (no DB, no admin) |
| `db_migrate_only` | `migrate.sh` only |
| `db_bootstrap_only` | `bootstrap.sh` once |
| `data_services_only` | PG/PostGIS/Redis install script |
| `install_systemd` | `deploy/staging/install_systemd.sh` + restart |
| `nginx_tls` | `deploy/staging/install_nginx_tls.sh` — nginx + certbot for `api-stg` / `admin-stg` ([`STAGING_NGINX_TLS.md`](./STAGING_NGINX_TLS.md); secret **`STAGING_CERTBOT_EMAIL`**) |

Set **git_ref** to any branch (e.g. `dev`). Prod uses the same pattern in **Deploy production** when rollout is wired.

**HTTPS edge (Step 2):** After Wix A records point at `stg-aio-1`, run **Deploy staging** with **`component=nginx_tls`** (manual only). Requires GitHub Environment secret **`STAGING_CERTBOT_EMAIL`** (Let’s Encrypt contact).

**Redis micro:** **Deploy Redis staging** → `terraform_action=apply`, then set `REDIS_URL` from terraform output on `stg-aio-1` and `STAGING_SKIP_HOST_REDIS=true`.

**DB audit:** **DB verify** on staging; optional **compare_dev** if GitHub Environment secret `DEV_DATABASE_URL` is set (laptop/dev read-only URL).

```bash
# On VM or laptop with URLs:
python scripts/verify_database_schema.py --strict --label staging
python scripts/compare_database_schemas.py --left-url "$DEV_DATABASE_URL" --right-url "$DATABASE_MIGRATE_URL" --strict
```

---

## First-time on VM (before CD works)

Run **once** on `stg-aio-1` (SSH):

```bash
sudo mkdir -p /opt/mana-guruji && sudo chown opc:opc /opt/mana-guruji
mkdir -p /opt/mana-guruji/src
git clone -b dev https://github.com/svasthol/puja_platform.git /opt/mana-guruji/src/puja_platform
cd /opt/mana-guruji/src/puja_platform

# S3 — data services
chmod +x scripts/linux/install_data_services_ol9.sh
./scripts/linux/install_data_services_ol9.sh

# S2 — Python venv
export VENV_DIR=/opt/mana-guruji/venv
./scripts/linux/bootstrap_python_runtime.sh

# Config
sudo mkdir -p /etc/mana-guruji
sudo cp deploy/env/staging.api.env.example /etc/mana-guruji/api.env
sudo chmod 600 /etc/mana-guruji/api.env
# EDIT passwords, Razorpay test keys, OCI S3 keys

# S4 — roles (once)
set -a && source /etc/mana-guruji/api.env && set +a
export DATABASE_URL="$DATABASE_ADMIN_URL"
./scripts/bootstrap.sh
./scripts/migrate.sh

# S5 — systemd
chmod +x deploy/staging/install_systemd.sh
./deploy/staging/install_systemd.sh
sudo systemctl start mana-guruji-api mana-guruji-celery-worker mana-guruji-celery-beat

# Admin UI (Model 2)
chmod +x deploy/staging/install_admin.sh
./deploy/staging/install_admin.sh
# Add http://140.245.245.201:3000 to ALLOWED_ORIGINS in api.env if not already, then restart API
```

Or use **Actions → Deploy staging → Run workflow** with:

- `run_data_services` = true (first time only)
- `run_db_bootstrap` = true (once, after `api.env` exists)

---

## Scripts reference

| Script | When |
|--------|------|
| [`install_data_services_ol9.sh`](../../scripts/linux/install_data_services_ol9.sh) | Once: PG16 + PostGIS + Redis |
| [`bootstrap_python_runtime.sh`](../../scripts/linux/bootstrap_python_runtime.sh) | Every deploy (idempotent pip) |
| [`bootstrap.sh`](../../scripts/bootstrap.sh) | Once per DB (roles) |
| [`migrate.sh`](../../scripts/migrate.sh) | Every deploy |
| [`remote_staging_deploy.sh`](../../scripts/linux/remote_staging_deploy.sh) | Called by GitHub SSH |
| [`install_admin.sh`](../../deploy/staging/install_admin.sh) | Admin UI build + `mana-guruji-admin` — [`STAGING_ADMIN_UI.md`](./STAGING_ADMIN_UI.md) |

---

## GitHub setup

[`STAGING_GITHUB_SETUP.md`](./STAGING_GITHUB_SETUP.md) — Environment **`staging`** secrets.

---

## Laptop workflow (daily)

```powershell
cd C:\OM\Guruji\mana_guruji\puja_platform
git checkout dev
git pull
# ... commit ...
git push origin dev
```

Watch **Actions** → **Deploy staging** → green health step.

**Do not** SSH `git pull` on prod path for routine releases — use pipeline after `dev` is stable; promote to `main` for prod later.

---

## Production (later)

Same scripts on **app-1/app-2** with Patroni + PgBouncer; `deploy-prod.yml` rollout + digest pin — **preflight only today**.

**STG → prod promotion, gates, and pipelines to build:** [`STG_TO_PROD_PIPELINE.md`](./STG_TO_PROD_PIPELINE.md) (incident log → prod guardrails: [`STAGING_DEPLOY_INCIDENTS.md`](./STAGING_DEPLOY_INCIDENTS.md)).
