# GitHub Actions ↔ OCI fleet

**Compute single source of truth:** [`spec/plans/OCI_COMPUTE_FLEET.md`](../spec/plans/OCI_COMPUTE_FLEET.md)  
**Machine-readable fleet:** [`infra/oci/fleet.launch.yaml`](../infra/oci/fleet.launch.yaml)

## Workflows (backend `puja_platform`)

| Workflow | Purpose | Fleet coupling |
|----------|---------|----------------|
| [`workflows/deploy-prod.yml`](./workflows/deploy-prod.yml) | Prod preflight (G1/G2); deploy placeholder | Targets **`app-1` / `app-2`** when SSH/OCIR rollout is wired; images **`linux/arm64`** |
| `workflows/ci.yml` | *Planned* — pytest, migrate chain | Runners `ubuntu-latest`; optional **`ubuntu-24.04-arm`** or OL9 A1 job for arm64 wheel check |
| `workflows/build-push.yml` | *Planned* — OCIR `hyd.ocir.io` | **`platforms: linux/arm64`** per fleet SSOT |
| `workflows/deploy-staging.yml` | *Planned* | Single host **`stg-aio-1`** |

## Secrets / environments

| GitHub Environment | Hosts | Typical secrets |
|--------------------|-------|-----------------|
| `production` | `app-1`, `app-2` (deploy); DB via HAProxy | `DATABASE_URL` (PgBouncer), `DATABASE_ADMIN_URL` (primary `:5000`) |
| `staging` | `stg-aio-1` | Staging DB/Redis URLs |

## IaC migration checklist

- [x] Staging Terraform: `infra/oci/terraform/environments/staging` (`stg-aio-1`) — tracker [`OCI_INFRA_STATUS.md`](../spec/plans/OCI_INFRA_STATUS.md)
- [ ] `terraform apply` staging + inventory filled
- [ ] Terraform module variables default from `fleet.launch.yaml` (`region`, `shape`, per-host `ocpu`, `memory_gb`) for **production**
- [ ] Ansible inventory generated from `environments.production.hosts`
- [ ] NLB health path = `load_balancer.health_check.path` in YAML
- [ ] No E4 or 9-VM resources unless `profile` changes in a reviewed PR
