# GitHub Actions ↔ OCI fleet

**Compute single source of truth:** [`spec/plans/OCI_COMPUTE_FLEET.md`](../spec/plans/OCI_COMPUTE_FLEET.md)  
**Machine-readable fleet:** [`infra/oci/fleet.launch.yaml`](../infra/oci/fleet.launch.yaml)

## Workflows (backend `puja_platform`)

| Workflow | Purpose | Fleet coupling |
|----------|---------|----------------|
| [`workflows/deploy-prod.yml`](./workflows/deploy-prod.yml) | Prod preflight (G1/G2); deploy placeholder | Targets **`app-1` / `app-2`** when SSH/OCIR rollout is wired; images **`linux/arm64`** |
| [`workflows/ci.yml`](./workflows/ci.yml) | **linux-arm64-runtime** + G1/G2 preflight | `ubuntu-24.04-arm` |
| [`workflows/deploy-staging.yml`](./workflows/deploy-staging.yml) | Manual SSH bootstrap | Secrets: [`STAGING_GITHUB_SETUP.md`](../spec/plans/STAGING_GITHUB_SETUP.md) |
| [`workflows/infra-terraform-staging.yml`](./workflows/infra-terraform-staging.yml) | PR plan (optional) | Staging compute already applied locally |
| `workflows/build-push.yml` | *Planned* — OCIR `hyd.ocir.io` | **`platforms: linux/arm64`** |

## Secrets / environments

| GitHub Environment | Hosts | Typical secrets |
|--------------------|-------|-----------------|
| `production` | `app-1`, `app-2` (deploy); DB via HAProxy | `DATABASE_URL` (PgBouncer), `DATABASE_ADMIN_URL` (primary `:5000`) |
| `staging` | `stg-aio-1` | Staging DB/Redis URLs |

## IaC migration checklist

- [x] Staging Terraform apply + inventory (**2026-10-16**)
- [x] `ci.yml` + `deploy-staging.yml` + `infra-terraform-staging.yml` in repo
- [ ] GitHub Environment `staging` secrets configured
- [ ] Staging S2–S6 on VM + `/health` — [`OCI_INFRA_STATUS.md`](../spec/plans/OCI_INFRA_STATUS.md)
- [ ] Terraform module variables default from `fleet.launch.yaml` (`region`, `shape`, per-host `ocpu`, `memory_gb`) for **production**
- [ ] Ansible inventory generated from `environments.production.hosts`
- [ ] NLB health path = `load_balancer.health_check.path` in YAML
- [ ] No E4 or 9-VM resources unless `profile` changes in a reviewed PR
