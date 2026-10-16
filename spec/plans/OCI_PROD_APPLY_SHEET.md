# OCI production apply sheet — step by step

**Purpose:** Single checklist for **first production cut** on OCI (`ap-hyderabad-1`).  
**How to use:** Complete rows **in order**. Mark **Manual** steps on the server or console; **CI/Ansible** when those pipelines exist.

**Repos:** Backend only — `puja_platform` ([Guruji](https://github.com/svasthol/Guruji.git)). Flutter is separate ([PujaPlatformFlutter](https://github.com/svasthol/PujaPlatformFlutter.git)).

**Related:** [`OCI_COMPUTE_FLEET.md`](./OCI_COMPUTE_FLEET.md) · [`OCI_INFRA_STATUS.md`](./OCI_INFRA_STATUS.md) (**IaC apply tracker**) · [`infra/oci/terraform/environments/staging`](../../infra/oci/terraform/environments/staging) · [`OCI_PROD_MANUAL_RUNBOOK.md`](./OCI_PROD_MANUAL_RUNBOOK.md) · [`.github/OCI_CI_CD.md`](../../.github/OCI_CI_CD.md).

---

## Legend

| Mode | Meaning |
|------|---------|
| **MANUAL** | You run it once (console, SSH, Bastion, or one-off shell). Not replaced by git push alone. |
| **ANSIBLE** | Target: `infra/oci/ansible` (when implemented). |
| **TERRAFORM** | Target: `infra/oci/terraform` (when implemented). |
| **CI** | GitHub Actions (`deploy-staging.yml` / `deploy-prod.yml`). |
| **RUNTIME** | Long-lived process (systemd / Podman quadlet) after cutover. |

---

## Phase 0 — OCI account & network (before any app)

| # | Step | Mode | Where | Done |
|---|------|------|-------|------|
| 0.1 | Tenancy **home region** = `ap-hyderabad-1` | **MANUAL** | OCI Console | ☐ |
| 0.1b | **Compartment** per env (`mana-guruji-staging` / `mana-guruji-production`) | **MANUAL** | OCI CLI or Console — [`OCI_COMPARTMENTS.md`](./OCI_COMPARTMENTS.md) | Staging ☑ · Prod ☐ |
| 0.2 | VCN, public + private subnets, IGW, NAT, SGW, NSGs | **TERRAFORM** or **MANUAL** | OCI | ☐ |
| 0.3 | Provision VMs per **[`OCI_COMPUTE_FLEET.md`](./OCI_COMPUTE_FLEET.md)** / [`fleet.launch.yaml`](../../infra/oci/fleet.launch.yaml); fill inventory | **TERRAFORM** or **MANUAL** | OCI Compute | ☐ |
| 0.4 | NLB → app nodes `:443` / `:80`; health check **`/health/live`** | **TERRAFORM** or **MANUAL** | OCI LB | ☐ |
| 0.5 | Object Storage buckets: `kyc`, `catalog`, `pg-backups`; Vault secrets | **TERRAFORM** or **MANUAL** | OCI | ☐ |
| 0.6 | DNS: `api.<domain>`, `admin.<domain>` → NLB | **MANUAL** | OCI DNS or registrar | ☐ |

---

## Phase 1 — Data tier (DB + Redis) — **MANUAL / ANSIBLE until playbooks land**

| # | Step | Mode | Where | Done |
|---|------|------|-------|------|
| 1.1 | Install PG16 + PostGIS on `db-1` / `db-2`; Patroni + etcd; HAProxy on app nodes (`:5000` primary) | **ANSIBLE** / **MANUAL** | `db-*`, `app-*` | ☐ |
| 1.2 | Install Redis + Sentinel on app/cache nodes; AOF | **ANSIBLE** / **MANUAL** | `cache-1`, `app-*` | ☐ |
| 1.3 | Install **PgBouncer** (transaction mode) on **app-1** and **app-2** | **ANSIBLE** / **MANUAL** | `app-*` | ☐ |
| 1.4 | pgBackRest → Object Storage; first full backup | **MANUAL** | `cache-1` or db | ☐ |

---

## Phase 2 — **One-time database bootstrap** (new empty prod DB only)

**Is `bash scripts/bootstrap.sh` manual in prod OCI?**  
**Yes.** Run it **once per new production database**, from a host that can reach Postgres **as superuser** (Bastion → `app-1`, or jump to `db-1` before Patroni hardening). It is **not** run on every deploy and **not** run from your laptop unless you VPN/Bastion to the private network.

| # | Step | Mode | Who / connection | Done |
|---|------|------|------------------|------|
| 2.1 | Create database `Mana_Guruji` (if not exists) | **MANUAL** | Superuser on primary | ☐ |
| 2.2 | **`CREATE EXTENSION`** `pgcrypto`, `btree_gist`, `postgis` | **MANUAL** | Superuser on `Mana_Guruji` — extensions need superuser | ☐ |
| 2.3 | Clone repo on jump host; Python venv + `pip install -r requirements.txt` | **MANUAL** | e.g. `app-1` | ☐ |
| 2.4 | Set **`DATABASE_URL`** to **superuser** URL to primary (**HAProxy :5000**, not PgBouncer) | **MANUAL** | Shell on jump host | ☐ |
| 2.5 | Run **`bash scripts/bootstrap.sh`** | **MANUAL** | Same shell — creates **`puja_app`** + **`puja_migrate`** + default privileges | ☐ |
| 2.6 | Change **`dev_password`** on `puja_app` / `puja_migrate` in prod; store in **OCI Vault** | **MANUAL** | `psql` + Vault | ☐ |

**Commands (on jump host, after 2.3–2.4):**

```bash
cd /opt/mana-guruji/puja_platform   # or your clone path
source .venv/bin/activate
export DATABASE_URL='postgresql://postgres:SUPERPASS@<haproxy-primary>:5000/Mana_Guruji'
bash scripts/bootstrap.sh
```

**Windows laptop (only if Bastion/SSH to Linux jump):** use Git Bash or SSH to `app-1` — do **not** run bootstrap against prod from a local PC without network path to the DB.

**Never again on same DB:** bootstrap is idempotent but only needed once; **every deploy** uses `migrate.sh` + `apply_grants.py` (CI later).

---

## Phase 3 — Schema & seed (one-time for new prod DB)

| # | Step | Mode | Connection | Done |
|---|------|------|------------|------|
| 3.1 | `alembic upgrade head` (001–011) | **MANUAL** then **CI** | **`puja_migrate`** or superuser via **:5000** | ☐ |
| 3.2 | `python scripts/apply_migration_012.py` … `027.py` | **MANUAL** then **CI** | Same | ☐ |
| 3.3 | `python scripts/apply_migrations_028_032.py` | **MANUAL** then **CI** | Same | ☐ |
| 3.4 | `python scripts/apply_grants.py` | **MANUAL** then **every deploy** | Superuser or role that can run grants SQL | ☐ |
| 3.5 | `python scripts/check_tds_readiness.py --strict` | **MANUAL** | Migrate URL | ☐ |
| 3.6 | Catalog / Hyderabad seed (`bootstrap_catalog.py`, ops data) | **MANUAL** | Per [`CATALOG_SYNC.md`](./CATALOG_SYNC.md) | ☐ |
| 3.7 | `python scripts/bootstrap_admin.py` + `TOTP_ENC_KEYS` in Vault | **MANUAL** | Superuser / admin URL | ☐ |

**Important:** Migrations must **not** use PgBouncer `:6432`. Use **HAProxy → primary :5000** (see plan `migrate.sh`).

---

## Phase 4 — App runtime on OCI (first cut)

| # | Step | Mode | Where | Done |
|---|------|------|-------|------|
| 4.1 | Render secrets to `/etc/mana-guruji/api.env` from Vault | **MANUAL** / **ANSIBLE** | `app-*` | ☐ |
| 4.2 | Runtime **`DATABASE_URL`** = `postgresql+psycopg://puja_app:…@127.0.0.1:6432/Mana_Guruji` (PgBouncer local) | **MANUAL** | `api.env` | ☐ |
| 4.3 | Deploy API + workers + beat (Podman quadlets or systemd) | **CI** / **MANUAL** | `app-*` | ☐ |
| 4.4 | nginx TLS on app nodes; NLB → backends | **MANUAL** / **ANSIBLE** | `app-*` | ☐ |
| 4.5 | Razorpay / Setu webhook URLs → public `https://api.<domain>/...` | **MANUAL** | Vendor dashboards | ☐ |
| 4.6 | `GET https://api.<domain>/health` → ok; `sweep_age_seconds` sane | **MANUAL** | curl / monitor | ☐ |

**G1 (PgBouncer):** App image must include `prepare_threshold=None` on engine + `get_connection()` (shipped in repo).

---

## Phase 5 — GitHub / deploy pipeline (when wired)

| # | Step | Mode | Notes | Done |
|---|------|------|-------|------|
| 5.1 | GitHub Environment **`production`**: secrets `DATABASE_URL` (PgBouncer), `DATABASE_ADMIN_URL` (primary :5000) | **MANUAL** | For `deploy_preflight_live.py` | ☐ |
| 5.2 | Run **`deploy-prod.yml`** workflow_dispatch | **CI** | Repo preflight + live preflight | ☐ |
| 5.3 | Future: image digest promote + rolling restart | **CI** | Placeholder deploy job today | ☐ |

---

## Phase 6 — Mobile & admin (separate from DB bootstrap)

| # | Step | Mode | Repo | Done |
|---|------|------|------|------|
| 6.1 | OpenAPI sync → Flutter; prod `API_BASE_URL` | **MANUAL** | PujaPlatformFlutter | ☐ |
| 6.2 | Admin UI deploy + `ALLOWED_ORIGINS` | **MANUAL** / **CI** | Guruji `admin_ui/` | ☐ |
| 6.3 | Device smoke F5/F6 on **staging** then prod | **MANUAL** | [`MVP_GO_NO_GO_CHECKLIST.md`](./MVP_GO_NO_GO_CHECKLIST.md) | ☐ |

---

## Every production deploy (after go-live)

| # | Step | Mode | Notes |
|---|------|------|-------|
| D.1 | `deploy-prod.yml` preflight (repo + live) | **CI** | Fails if G1/G2 code or DB roles missing |
| D.2 | `migrate.sh` as **`puja_migrate`** via **:5000** | **CI** / **MANUAL** | Not through PgBouncer |
| D.3 | `python scripts/apply_grants.py` | **CI** / **MANUAL** | Every deploy |
| D.4 | Rolling restart API/workers (NLB drain) | **CI** / **MANUAL** | Per plan |
| D.5 | Smoke: `/health`, one booking path | **MANUAL** | Optional automated |

**Do not re-run `bootstrap.sh` on every deploy** — only **D.2–D.4**.

---

## Quick answers

| Question | Answer |
|----------|--------|
| Is `bash scripts/bootstrap.sh` manual on OCI prod? | **Yes — once** per new prod database, on a jump host with superuser URL to primary (**:5000**). |
| From my Windows PC in `mana_guruji\puja_platform`? | **Only** if you SSH/Bastion to a Linux host in the VCN; not over the public internet to Postgres. |
| Does CI run bootstrap? | **No** (by design). CI runs **preflight**, **migrate**, **grants**, **deploy**. |
| Staging vs prod | **Separate DB.** Run Phase 2–3 on **staging** first; repeat Phase 2–3 on **fresh prod** (never clone staging data wholesale). |

---

## Sign-off (prod go-live)

| Role | Name | Date | ☐ |
|------|------|------|---|
| Ops / infra | | | |
| Engineering | | | |

*Last updated: fleet SSOT [`OCI_COMPUTE_FLEET.md`](./OCI_COMPUTE_FLEET.md); bootstrap/G1/G2 preflight unchanged.*
