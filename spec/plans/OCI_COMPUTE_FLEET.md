# OCI compute fleet — single source of truth (SSOT)

**Purpose:** One place for **hostname, shape, OCPU, RAM, disk, OS, and region** so manual ops, **Terraform/Ansible**, and **GitHub Actions** stay aligned.

| Artifact | Path | Use |
|----------|------|-----|
| **This document** | `spec/plans/OCI_COMPUTE_FLEET.md` | Humans, reviews, runbooks |
| **IaC status** | [`OCI_INFRA_STATUS.md`](./OCI_INFRA_STATUS.md) | Staging/prod apply checklist |
| **Compartments** | [`OCI_COMPARTMENTS.md`](./OCI_COMPARTMENTS.md) | `mana-guruji-staging` / `mana-guruji-production` |
| **Launch fleet (chosen)** | [`infra/oci/fleet.launch.yaml`](../../infra/oci/fleet.launch.yaml) | IaC generators, CI deploy matrix |
| **Terraform staging** | [`infra/oci/terraform/environments/staging`](../../infra/oci/terraform/environments/staging) | `stg-aio-1` apply |
| **9-VM alternative** | [`infra/oci/fleet.alternative-9vm.yaml`](../../infra/oci/fleet.alternative-9vm.yaml) | **Not chosen** — do not apply |
| **Apply order** | [`OCI_PROD_APPLY_SHEET.md`](./OCI_PROD_APPLY_SHEET.md) | Phases 0–6 |
| **SSH procedures** | [`OCI_PROD_MANUAL_RUNBOOK.md`](./OCI_PROD_MANUAL_RUNBOOK.md) | Per-host install |
| **Workflows** | [`.github/OCI_CI_CD.md`](../../.github/OCI_CI_CD.md) | Actions ↔ fleet mapping |

**Rule:** If a value conflicts with another doc, **`fleet.launch.yaml` + this file win**. Update YAML and this MD together in the same PR.

---

## Region and platform defaults (launch)

| Field | Value |
|-------|--------|
| **Region** | `ap-hyderabad-1` |
| **Chosen profile** | `option_b_corrected` (MVP 5-node) |
| **Shape (all launch hosts)** | `VM.Standard.A1.Flex` |
| **Processor** | Ampere **aarch64** |
| **OS** | **Oracle Linux 9** (marketplace image) |
| **SSH user** | `opc` |
| **Default boot disk** | **50 GB**, balanced performance |
| **DB data disk** | **100 GB** block volume per `db-*`, balanced **10 VPUs**, mount `/var/lib/postgresql` |
| **Container / image CI** | `linux/arm64` (match A1) |

---

## Production hosts — Option B (corrected)

| Hostname | Role | OCPU | RAM (GB) | Boot (GB) | Extra volumes | Public IP |
|----------|------|-----:|---------:|----------:|---------------|-----------|
| `app-1` | FastAPI, Celery workers, RedBeat, PgBouncer, HAProxy `:5000`, etcd, Sentinel | 2 | 12 | 50 | — | Optional (Bastion preferred) |
| `app-2` | Same + **Redis replica** | 2 | 12 | 50 | — | Optional |
| `db-1` | PostgreSQL 16 + PostGIS, Patroni | 2 | 12 | 50 | **100 GB** data | **No** |
| `db-2` | Patroni replica (**identical** to db-1) | 2 | 12 | 50 | **100 GB** data | **No** |
| `cache-1` | Redis primary, etcd, Sentinel, pgBackRest | 1 | 6 | 50 | Optional staging for backups | **No** |

**NLB:** TLS at load balancer → `app-1`, `app-2` **`:8000` (uvicorn)**. **No nginx on prod app nodes.** Health check **`GET /health/live`** only.

**Staging:** **nginx** on `stg-aio-1` only — HTTPS edge to local API (see [`STAGING_CONFIG_ROLLOUT.md`](./STAGING_CONFIG_ROLLOUT.md)).

---

## Staging (non-prod)

| Hostname | OCPU | RAM (GB) | Boot (GB) | Notes |
|----------|-----:|---------:|----------:|-------|
| `stg-aio-1` | 1 | 6 | **50** | PG + Redis + API + **nginx (TLS edge)** + Celery on one VM; **always-on** (no stop/start per deploy) |

Use for **OL9 + aarch64** `pip install -r requirements.txt` gate before prod fleet.

---

## Post-launch scale (not day-one)

| Hosts | Change | Trigger |
|-------|--------|---------|
| `app-1`, `app-2` | **2 → 4 OCPU** on `VM.Standard.A1.Flex` (RAM 12 GB unless OOM) | After **load test**; change ticket required |

Do **not** set 4 OCPU on app nodes in Terraform/Console for initial go-live.

---

## Software versions (runtime — all environments)

| Component | Version | Doc |
|-----------|---------|-----|
| Python | **3.12.x** | [`STACK_VERSIONS.md`](../STACK_VERSIONS.md) |
| PostgreSQL | **16.x** | MVP checklist B3 |
| PostGIS | **≥ 3.4** | MVP checklist B3 |
| Redis | **7.x** | AOF + Sentinel |

---

## CI/CD connection points

| Concern | Value | Where enforced (current / planned) |
|---------|-------|-----------------------------------|
| Image architecture | `linux/arm64` | Future `build-push.yml` → OCIR |
| Deploy rolling set | `app-1`, `app-2` | Future `deploy-prod.yml` deploy job |
| Migrate / bootstrap DB path | HAProxy **`:5000`** (not PgBouncer **`:6432`**) | `migrate.sh`, manual runbook §4.6 |
| Runtime app `DATABASE_URL` | `127.0.0.1:6432` (PgBouncer local) | App env on app nodes |
| Preflight | G1/G2 | `.github/workflows/deploy-prod.yml` |

---

## Alternative fleet — **not chosen**

Nine-VM split with **E4** Postgres primary — **do not** use for launch. Full machine-readable spec: [`infra/oci/fleet.alternative-9vm.yaml`](../../infra/oci/fleet.alternative-9vm.yaml).

| Role | Shape | OCPU | RAM | Block | Count |
|------|-------|-----:|----:|------:|------:|
| Nginx | A1.Flex | 2 | 2 GB | 30 GB | 2 |
| FastAPI + PgBouncer | A1.Flex | 2 | 4 GB | 40 GB | 2 |
| Celery + beat | A1.Flex | 2 | 4 GB | 40 GB | 1 |
| Redis | A1.Flex | 2 | 2 GB | 30 GB | 2 |
| Postgres primary | **E4.Flex** | 4 | 16 GB | 200 GB | 1 |
| Postgres replica | A1.Flex | 2 | 8 GB | 200 GB | 1 |

Legacy cost write-up (local only, not in Guruji git): `mana_guruji/infra/OCI_COMPUTE_SPEC.md`.

---

## Inventory worksheet (fill at provision time)

| Hostname | OCID | Private IP | Subnet | Compartment |
|----------|------|------------|--------|-------------|
| app-1 | | | app-private | |
| app-2 | | | app-private | |
| db-1 | | | data-private | |
| db-2 | | | data-private | |
| cache-1 | | | data-private | |
| stg-aio-1 | `…vlukjq` *(full OCID in OCI_INFRA_STATUS)* | `10.60.1.98` | staging public | `mana-guruji-staging` |

---

## Terraform (staging)

| Item | Value |
|------|--------|
| Module | `infra/oci/terraform/modules/staging_stack` |
| Environment | `infra/oci/terraform/environments/staging` |
| Creates | VCN `10.60.0.0/16`, public subnet, **`stg-aio-1`** instance |
| Vars file | Copy `terraform.tfvars.example` → `terraform.tfvars` (gitignored) |
| Apply status | **Done 2026-10-16** — public IP `140.245.245.201` |

Progress: [`OCI_INFRA_STATUS.md`](./OCI_INFRA_STATUS.md) (**S1–S6** post-apply).

---

## Change log

| Date | Change |
|------|--------|
| 2026-10-16 | Staging `terraform apply` — `stg-aio-1` provisioned |
| 2026-10-10 | Staging Terraform scaffold for `stg-aio-1` |
| 2026-10-10 | SSOT created; Option B corrected; YAML for IaC/CI |
