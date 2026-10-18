# Terraform — OCI (Mana Guruji)

**Fleet SSOT:** [`spec/plans/OCI_COMPUTE_FLEET.md`](../../../spec/plans/OCI_COMPUTE_FLEET.md) · [`fleet.launch.yaml`](../fleet.launch.yaml)  
**IaC status tracker:** [`spec/plans/OCI_INFRA_STATUS.md`](../../../spec/plans/OCI_INFRA_STATUS.md)  
**Local auth:** [`LOCAL_OCI_SETUP.md`](../LOCAL_OCI_SETUP.md)

## Layout

| Path | Purpose |
|------|---------|
| [`environments/staging/`](./environments/staging/) | **`stg-aio-1`** — VCN + public subnet + A1 instance (OL9 aarch64) |
| [`modules/staging_stack/`](./modules/staging_stack/) | Reusable staging network + compute |
| `environments/production/` | *Planned* — 5-node Option B |

## Quick start (staging)

```powershell
cd C:\OM\Guruji\mana_guruji\puja_platform\infra\oci\scripts
. .\Set-OciConfig.ps1   # required for terraform (exports TF_VAR_* from .oci/config)

cd ..\terraform\environments\staging
copy terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars: compartment_id, ssh_public_key, ssh_allowed_cidrs

terraform init
terraform plan
terraform apply
```

**Laptop DB parity:** Postgres via `ssh -L 15432:127.0.0.1:5432` (not public 5432). App ingress: `developer_allowed_cidrs` (8000/3000/6379) — see [`spec/plans/DB_DEV_STAGING_PARITY.md`](../../../spec/plans/DB_DEV_STAGING_PARITY.md).

Record outputs (`public_ip`, `instance_id`) in [`OCI_COMPUTE_FLEET.md`](../../../spec/plans/OCI_COMPUTE_FLEET.md) inventory and [`OCI_INFRA_STATUS.md`](../../../spec/plans/OCI_INFRA_STATUS.md).

## State

Staging uses **local state** (`terraform.tfstate` in `environments/staging/`, gitignored).  
Production will move to **OCI Object Storage** backend (see `backend.tf` comment in staging).

## Provider

Uses `oracle/oci` with the same API key as OCI CLI (`OCI_CLI_CONFIG_FILE`).
