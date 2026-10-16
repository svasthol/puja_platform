# Staging deploy pipeline (dev laptop → GitHub → OCI)

**Host:** `stg-aio-1` · **Target branch:** `dev` · **Inventory:** [`OCI_INFRA_STATUS.md`](./OCI_INFRA_STATUS.md)

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
    ↓
[GitHub]  curl http://127.0.0.1:8000/health/live via SSH
```

**Terraform** for staging compute is **already applied** — not part of app deploy. Optional: [`infra-terraform-staging.yml`](../../.github/workflows/infra-terraform-staging.yml) on IaC PRs.

---

## Workflows

| Workflow | Trigger | Role |
|----------|---------|------|
| [`ci.yml`](../../.github/workflows/ci.yml) | push/PR `main`, `dev` | Compile-time: arm64 wheels + import verify |
| [`deploy-staging.yml`](../../.github/workflows/deploy-staging.yml) | push `dev` (app paths) or **manual** | Runtime deploy on VM |
| [`deploy-prod.yml`](../../.github/workflows/deploy-prod.yml) | manual | Prod preflight (rollout TBD) |

---

## First-time on VM (before CD works)

Run **once** on `stg-aio-1` (SSH):

```bash
sudo mkdir -p /opt/mana-guruji && sudo chown opc:opc /opt/mana-guruji
git clone https://github.com/svasthol/Guruji.git /opt/mana-guruji/src
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

Same scripts on **app-1/app-2** with Patroni + PgBouncer; `deploy-prod.yml` rollout + digest pin — not enabled yet.
