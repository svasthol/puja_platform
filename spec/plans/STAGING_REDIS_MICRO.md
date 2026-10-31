# Staging Redis on E2 Micro (IaC) — before Celery hardening

**Important:** This VM runs **Redis only**. **Celery worker + beat stay on `stg-aio-1`** (systemd). Celery **uses** Redis as broker; it is not installed on the micro.

| Host | Shape | Role |
|------|--------|------|
| `stg-aio-1` | A1 ARM | Postgres, FastAPI, **Celery worker**, Celery beat |
| `stg-redis-1` | **VM.Standard.E2.1.Micro** (Always Free x86) | Docker **redis:7-alpine**, port **6379** |

## Phase 1 — Provision Redis (Terraform)

1. In `infra/oci/terraform/environments/staging/terraform.tfvars`:

```hcl
enable_staging_redis_micro = true
# Optional: reach Redis from laptop (not required for app — app uses private IP)
# redis_extra_client_cidrs = ["YOUR_PUBLIC_IP/32"]
```

2. Apply (laptop) or **Actions → Deploy Redis staging** → `terraform_action=apply` (needs OCI secrets + remote state).

```bash
cd infra/oci/terraform/environments/staging
terraform plan
terraform apply
```

3. Note outputs:

| Output | Use |
|--------|-----|
| `stg_redis_private_ip` | App traffic (preferred) |
| `stg_redis_public_ip` | SSH + optional external Redis |
| `stg_redis_url` | `redis://<private>:6379/0` → **REDIS_URL** on aio |
| `stg_redis_url_celery` | `redis://<private>:6379/1` → Celery (phase 2 wiring) |
| `stg_redis_url_public` | Only if `redis_extra_client_cidrs` includes your IP |

**Redis “database name”:** Redis uses **numeric DB indexes** (`/0`, `/1`), not names like `redis_puja_db`. Convention in this repo:

- **DB 0** — app cache / presence (`REDIS_DB_CACHE`, `REDIS_URL` …`/0`)
- **DB 1** — Celery broker + results (`REDIS_DB_CELERY`, phase 2)
- **DB 2** — presence (`REDIS_DB_PRESENCE`) when split

Use key prefix `redis_puja:` in application keys if you need a logical namespace (optional).

4. Wait **5–10 min** after apply for cloud-init (Docker CE + `docker pull`). On OL9 the old `packages: docker` cloud-config was insufficient — module now installs **docker-ce** via bootstrap script. If empty: SSH and run `scripts/linux/install_redis_docker_ol9.sh` (after `sed -i 's/\r$//' ~/install_redis_docker_ol9.sh` if scp'd from Windows) or check `/var/log/mana-guruji-redis-bootstrap.log`.

```bash
ssh opc@<stg_redis_public_ip>
docker ps
redis-cli -h 127.0.0.1 ping
```

5. On **stg-aio-1**:

```bash
redis-cli -h <stg_redis_private_ip> ping
```

6. Edit `/etc/mana-guruji/api.env`:

```bash
REDIS_URL=redis://<PRIVATE_IP>:6379/0
REDIS_DB_CACHE=0
REDIS_DB_CELERY=1
```

7. GitHub repo variable: **`STAGING_SKIP_HOST_REDIS=true`** (do not install host redis on aio).

8. **Deploy staging** → `install_systemd` or start units; `curl http://127.0.0.1:8000/health/live`.

## NSG / exposure

- **6379** from **10.60.1.0/24** (staging app subnet) — always.
- **6379** from extra CIDRs only if `redis_extra_client_cidrs` is set.
- Docker publishes **`0.0.0.0:6379`** on the micro; access is still gated by OCI NSG.

## Phase 2 — Celery (next)

- Wire `celery_app` to **DB 1** URL (today broker uses `REDIS_URL` /0 — split in code).
- Confirm worker + beat healthy: `systemctl status mana-guruji-celery-worker mana-guruji-celery-beat`.
- Beat schedules + queue depth smoke tests.

## IaC files

| Path | Purpose |
|------|---------|
| `modules/staging_redis_micro/` | E2 Micro, NSG, cloud-init Docker |
| `enable_staging_redis_micro` | Toggle in staging `terraform.tfvars` |
| `.github/workflows/deploy-redis-staging.yml` | CI Terraform plan/apply |
