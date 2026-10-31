# Staging → production pipeline (promotion model)

**Purpose:** Same discipline as **laptop → staging** (`dev` push → Actions → VM): nothing important on prod is hand-built on a server without going through git + CI/CD. Staging failures are captured so prod does not rediscover them.

**Day-to-day procedure (developers):** [`DEVELOPER_RELEASE_FLOW.md`](./DEVELOPER_RELEASE_FLOW.md) — laptop → `dev` → staging → PR to `main` → future prod.  
**Diagrams:** [`GITHUB_STG_PROD_DEPLOYMENT_DIAGRAM.md`](./GITHUB_STG_PROD_DEPLOYMENT_DIAGRAM.md)

**Related:**

| Doc | Role |
|-----|------|
| [`STAGING_DEPLOY_PIPELINE.md`](./STAGING_DEPLOY_PIPELINE.md) | **Live today:** `dev` → `deploy-staging.yml` → `stg-aio-1` |
| [`STAGING_DEPLOY_INCIDENTS.md`](./STAGING_DEPLOY_INCIDENTS.md) | **STG error log → prod guardrails** (update before prod cut) |
| [`STAGING_CONFIG_ROLLOUT.md`](./STAGING_CONFIG_ROLLOUT.md) | Ordered staging config (S3, catalog, KYC, Razorpay) |
| [`OCI_PROD_APPLY_SHEET.md`](./OCI_PROD_APPLY_SHEET.md) | Prod fleet cut order |
| [`.github/OCI_CI_CD.md`](../../.github/OCI_CI_CD.md) | Workflow inventory target state |
| PM: [`Mana_Guruji_OCI_PM_Tracker_Production.csv`](./project_pm/Mana_Guruji_OCI_PM_Tracker_Production.csv) | Prod tasks + **STG-GATE** |

---

## What exists today vs planned

```text
[Laptop]  commit → push origin dev
              ↓
[GitHub]    ci.yml (partial gate)
              ↓
[GitHub]    deploy-staging.yml (self-hosted on stg-aio-1)     ✅ operational
              ↓
[stg-aio-1] remote_staging_deploy.sh · manual workflows (db-verify, storage-smoke, …)

              ↓  STG-GATE: STG-S6 + VAL-004 + incident review  ☐ not passed yet

[Laptop]    merge/promote dev → main (tag or SHA pin TBD)
              ↓
[GitHub]    build-push.yml → OCIR digest                    ☐ not built
              ↓
[GitHub]    deploy-prod.yml (rolling app-1/app-2)           ☐ preflight only today
              ↓
[Prod]      Terraform/Ansible fleet · Vault · NLB · same scripts as staging roles
```

**Rule:** Routine prod releases **do not** use SSH `git pull` on app nodes. Promote the **same commit** (or image digest) that passed staging gates.

---

## Staging exit gate (before prod IaC spend)

Update PM row **STG-GATE** in the production CSV when all are **Completed**:

| ID | Criterion |
|----|-----------|
| STG-S6 | `/health/ready` not degraded (DB + Redis) |
| VAL-004 | MVP A–F on staging |
| VAL-001 | `db-verify` strict vs `spec/db` |
| STG-CFG-004..005 | Catalog seed + admin image upload smoke (after storage) |
| **INC-REVIEW** | Walk [`STAGING_DEPLOY_INCIDENTS.md`](./STAGING_DEPLOY_INCIDENTS.md) §Production checklist; every new incident row has a prod action |

Storage (**STG-CFG-001..003**) is **Completed** as of 2026-10-24 (OCI buckets + `verify_staging_storage.py` on `7e54401`).

---

## Prod pipelines to build (mirror staging patterns)

Track in **production CSV** (`CI-002`, `CI-004`, `PRD-IAC-*`, `PRD-P0-005`). Build order:

| Order | Pipeline / artifact | Staging analogue | Prod target |
|-------|---------------------|------------------|-------------|
| 1 | `ci.yml` full (pytest + migrate chain on PostGIS) | CI-001b | Same; blocks bad merges |
| 2 | `build-push.yml` arm64 → OCIR, digest + Trivy | — | Pin digest in prod deploy |
| 3 | `infra-terraform` staging **apply** for buckets | STG-IAC-005 (optional) | **PRD-P0-005** buckets via Terraform, not console-only |
| 4 | `deploy-staging.yml` | ✅ | N/A |
| 5 | `staging-storage-smoke.yml` | CI-006 | **Prod:** same script, prod `api.env`, prod buckets (workflow TBD) |
| 6 | `deploy-prod.yml` beyond `preflight_only` | deploy-staging components | Rolling restart, migrate on DB role, approval gate |
| 7 | `rollback.yml` | — | Digest rollback |

**Config parity:** Anything in staging `api.env` that staging proved (S3 endpoint, checksum behavior via `app/services/s3_boto.py`, `ALLOWED_ORIGINS` JSON, DB URL `%40`) must land in **Vault + `deploy/env/*.env.example`** and Ansible/quadlet — not ad-hoc on prod VMs.

---

## “Do not repeat STG mistakes on prod” process

1. **When something breaks on staging** — add a row to [`STAGING_DEPLOY_INCIDENTS.md`](./STAGING_DEPLOY_INCIDENTS.md) (symptom, root cause, repo/ops fix).
2. **Same PR** (or immediate follow-up) — add or check the matching row in **§Production checklist** (IaC, pipeline, or runbook).
3. **Before STG-GATE** — PM reviews incident log; open prod tasks (**PRD-***) for any guardrail not yet in Terraform/Ansible/workflows.
4. **Prod cut** — use the **same code** that fixed staging (e.g. OCI S3: path-style + `request_checksum_calculation=when_required` in `s3_boto.py`, not only manual env exports).

Recent examples logged for prod:

| Staging lesson | Prod requirement |
|----------------|------------------|
| OCI S3 `put_object` **NotImplemented** (boto3 ≥1.36 checksums) | Ship `s3_boto.py`; run storage smoke in prod pipeline; optional `AWS_REQUEST_*` in Vault |
| VM `git reset --hard` / dirty clone | Prod deploy script always `checkout -f` pinned ref; no manual edits on fleet |
| Admin `NODE_ENV` before `npm ci` | Same `install_admin.sh` / systemd pattern on prod admin host |

---

## PM sync

When staging or prod pipeline work completes:

1. Update [`Mana_Guruji_OCI_PM_Tracker_Staging.csv`](./project_pm/Mana_Guruji_OCI_PM_Tracker_Staging.csv) or **Production** CSV.
2. Update [`STAGING_PENDING_CHECKLIST.md`](./project_pm/STAGING_PENDING_CHECKLIST.md) summary.
3. Bump **Last updated** in this file.

*Last updated: 2026-10-24*
