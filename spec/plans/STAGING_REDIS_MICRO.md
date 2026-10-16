# Staging Redis on E2 Micro (optional, IaC)

**Goal:** Run **Redis 7** in Docker on **`VM.Standard.E2.1.Micro`** (Always Free–eligible x86) in the **same staging VCN** as `stg-aio-1`. Postgres stays on **stg-aio-1** for now; app uses `REDIS_URL` pointing at the micro **private IP**.

## IaC

| Artifact | Purpose |
|----------|---------|
| `infra/oci/terraform/modules/staging_redis_micro/` | NSG (SSH + 6379 from app subnet), E2 Micro, cloud-init Docker + `redis:7-alpine` |
| `environments/staging/` variable `enable_staging_redis_micro` | Default `false`; set `true` in `terraform.tfvars` to create |

```hcl
enable_staging_redis_micro = true
```

Apply locally (same as staging stack):

```powershell
cd infra/oci/terraform/environments/staging
terraform plan
terraform apply
```

Outputs: `stg_redis_private_ip`, `stg_redis_url` → set on **stg-aio-1** in `/etc/mana-guruji/api.env`:

```bash
REDIS_URL=redis://10.60.x.x:6379/0
```

## App deploy pipeline

On **stg-aio-1**, install Postgres only (skip host Redis):

```bash
SKIP_REDIS=1 ./scripts/linux/install_data_services_ol9.sh
```

Or **Deploy staging** manual run with `run_data_services` after exporting `SKIP_REDIS=1` in `remote_staging_deploy.sh` (set repo variable `STAGING_SKIP_HOST_REDIS=true` when wired).

Wait ~2–3 minutes after Terraform apply for cloud-init to pull the image; verify on micro:

```bash
ssh opc@<stg-redis-1-public-ip>
docker ps
redis-cli -h 127.0.0.1 ping
```

From **stg-aio-1**:

```bash
redis-cli -h <stg-redis-private-ip> ping
```

## Later (prod / repeatability)

- Ansible role `redis_docker` mirroring cloud-init for drift repair.
- `cache-1` in prod fleet uses dedicated cache nodes (see `fleet.launch.yaml`); same pattern at larger scale.
