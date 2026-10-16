# GitHub Actions — staging setup

**VM:** `stg-aio-1` · `140.245.245.201` · inventory in [`OCI_INFRA_STATUS.md`](./OCI_INFRA_STATUS.md)

## Workflows

| Workflow | When | Purpose |
|----------|------|---------|
| [`ci.yml`](../../.github/workflows/ci.yml) | push/PR `main`, `dev` | **linux/arm64** pip + imports; G1/G2 preflight |
| [`deploy-staging.yml`](../../.github/workflows/deploy-staging.yml) | **Push `dev`** or manual | Full CD — [`STAGING_DEPLOY_PIPELINE.md`](./STAGING_DEPLOY_PIPELINE.md) |
| [`deploy-prod.yml`](../../.github/workflows/deploy-prod.yml) | Manual | Prod preflight (deploy TBD) |
| [`infra-terraform-staging.yml`](../../.github/workflows/infra-terraform-staging.yml) | PR touching `infra/oci/terraform/**` | `terraform plan` (optional if secrets set) |

## GitHub Environment: `staging`

Repository → **Settings → Environments → New environment** → `staging`

| Secret / variable | Example | Required for |
|-------------------|---------|----------------|
| `STAGING_HOST` | `140.245.245.201` | deploy-staging SSH |
| `STAGING_SSH_USER` | `opc` | deploy-staging |
| `STAGING_SSH_PRIVATE_KEY` | contents of private key matching VM `ssh_authorized_keys` | deploy-staging |
| `STAGING_COMPARTMENT_OCID` | staging compartment OCID | terraform plan in CI |
| `TERRAFORM_SSH_PUBLIC_KEY` | same key as terraform.tfvars | terraform plan in CI |

Optional **OCI_*** secrets for CI terraform plan: `OCI_TENANCY_OCID`, `OCI_USER_OCID`, `OCI_FINGERPRINT`, `OCI_PRIVATE_KEY`.

**Variable** `STAGING_REPO_DIR` (optional): `/opt/mana-guruji/src/puja_platform`

---

## Terraform on staging

**Already done locally:** VCN + `stg-aio-1` (no further Terraform until you add buckets, DNS, or prod).

CI `infra-terraform-staging.yml` is **optional** drift detection — not required for app install.

---

*See [`LINUX_RUNTIME_PIPELINE.md`](./LINUX_RUNTIME_PIPELINE.md) for on-VM bootstrap.*
