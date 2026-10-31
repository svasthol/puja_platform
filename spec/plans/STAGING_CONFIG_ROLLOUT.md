# Staging configuration rollout (ordered, code-aligned)

**Host:** `stg-aio-1` · **API env:** `/etc/mana-guruji/api.env` · **Admin env:** `/etc/mana-guruji/admin.env`  
**PM tracker:** [`Mana_Guruji_OCI_PM_Tracker_Staging.csv`](./project_pm/Mana_Guruji_OCI_PM_Tracker_Staging.csv) rows `STG-CFG-*`  
**Variable reference:** every `Settings` key is listed in [`ENV_STAGING_REFERENCE.md`](./ENV_STAGING_REFERENCE.md)

Execute **one phase at a time**. Mark the CSV row **Completed** only after its **Verify** step passes.

**Edge / TLS policy**

| Environment | Public HTTPS |
|-------------|----------------|
| **Staging** | **nginx on `stg-aio-1`** — reverse proxy **`:443` → `:8000`** (OCI DNS + cert). Acts as staging edge; not an OCI Load Balancer SKU. |
| **Production** | **OCI NLB** terminates TLS → **uvicorn `:8000` on `app-1` / `app-2`**. **No nginx on prod app VMs.** |

**Git / deploy procedure:** [`DEVELOPER_RELEASE_FLOW.md`](./DEVELOPER_RELEASE_FLOW.md) **§0 (mandatory `bug/*` / `feature/*` → PR `dev`)**; staging deploy tracks **`dev`**; config via `api.env` on VM.

---

## Principles (dev + staging)

| Rule | Why |
|------|-----|
| **Code only on `bug/*` or `feature/*`** — merge to `dev` via PR | See **DEVELOPER_RELEASE_FLOW §0**; no direct `dev`/`main` commits |
| Same **variable names** in laptop `.env` and VM `api.env` | One codebase (`app/core/config.py`) |
| **Different values** per environment | Secrets, URLs, buckets |
| **One line per key** in `api.env` | Duplicates (`S3_*` twice) silently break KYC vs catalog |
| Never commit secrets | Use `deploy/env/staging.api.env.example` as template only |
| Restart after `api.env` change | `sudo systemctl restart mana-guruji-api mana-guruji-celery-worker mana-guruji-celery-beat` |
| Admin UI separate | `NEXT_PUBLIC_API_URL` only in `admin.env`; rebuild via `install_admin.sh` if URL changes |

---

## Phase 0 — Baseline (done / keep stable)

| ID | Resource | Verify |
|----|----------|--------|
| STG-CFG-000 | VM, Postgres, Redis, migrate, API systemd | `curl -sS http://127.0.0.1:8000/health/live` |
| STG-CFG-000b | Admin Model 2 + CORS | Login at `:3000`; no `OPTIONS … 400` in API logs |

**Blindspot:** Deploy does not restart API if systemd units missing — run `deploy/staging/install_systemd.sh` once.

**Workflow:** `deploy-staging.yml` on push `dev` (paths `app/`, `deploy/`, `scripts/`, …).

---

## Phase 1 — Object Storage (catalog + KYC) **← start here**

### 1.1 OCI resources to create (manual or future Terraform)

| Resource | Recommended name | Notes |
|----------|------------------|--------|
| Bucket (catalog) | `mana-guruji-stg-catalog` | **Public** read for customer URLs (`S3_CATALOG_PUBLIC_URL`); admin upload via API presign |
| Bucket (KYC) | `mana-guruji-stg-kyc` | **Private**; presigned PUT/GET + server upload only |
| IAM | Policies in compartment `mana-guruji-staging` | Catalog: `any-user` read (optional). KYC: `Allow group … manage objects` on KYC bucket only — see [`OCI_OBJECT_STORAGE_IAM.md`](./OCI_OBJECT_STORAGE_IAM.md) |
| Customer secret key | One key pair in `api.env` | Same user as API S3 calls; staging smoke: `verify_staging_storage.py --strict` |
| Compat endpoint | `https://<namespace>.compat.objectstorage.ap-hyderabad-1.oraclecloud.com` | Must match `S3_REGION=ap-hyderabad-1` |

**Not in git yet:** Terraform module for buckets — track as `STG-IAC-005` (optional). Until then: **OCI Console + PM row**.

### 1.2 `api.env` block (concrete)

```env
S3_ENDPOINT_URL=https://<namespace>.compat.objectstorage.ap-hyderabad-1.oraclecloud.com
S3_REGION=ap-hyderabad-1
S3_ACCESS_KEY=<single-pair>
S3_SECRET_KEY=<single-pair>
S3_BUCKET_CATALOG=mana-guruji-stg-catalog
S3_BUCKET_KYC=mana-guruji-stg-kyc
# Optional later: S3_CATALOG_PUBLIC_URL=https://...
```

Update `deploy/env/staging.api.env.example` when names are final (placeholders only).

### 1.3 Verify (required)

```bash
sudo systemctl restart mana-guruji-api mana-guruji-celery-worker mana-guruji-celery-beat
set -a && source /etc/mana-guruji/api.env && set +a
/opt/mana-guruji/venv/bin/python scripts/verify_staging_storage.py --strict
```

**GitHub:** Actions → **Staging storage smoke** (`staging-storage-smoke.yml`).

### 1.4 Blindspots & fixes

| Blindspot | Symptom | Fix |
|-----------|---------|-----|
| Duplicate `S3_ACCESS_KEY` in `.env` | KYC works, catalog fails (or vice versa) | One pair; remove duplicates |
| Wrong endpoint / region | `head_bucket` 403/404 | Match OCI bucket region + compat URL |
| Empty `S3_ENDPOINT_URL` on OCI | Client hits AWS default | Set compat endpoint (required for OCI) |
| Expecting CSV upload in Admin UI | No bulk import screen | Use **Phase 2** bootstrap script for rows; images via Admin presign |
| Smoke `head_bucket OK` but `put/get NotImplemented` | boto3 ≥1.36 default S3 checksums + OCI compat | `s3_boto.py`: path-style + `request_checksum_calculation=when_required` — deploy `dev` + re-run smoke |

---

## Phase 2 — Catalogue **data** (Postgres, not S3)

Catalogue **text/categories/prices** live in **Postgres**. S3 only holds **image bytes**.

| Step | Command / action |
|------|------------------|
| 2.1 | `python scripts/bootstrap_catalog.py --force --deactivate-legacy` (on VM, `api.env` sourced) |
| 2.2 | `python scripts/check_catalog_readiness.py --strict` (optional gate) |
| 2.3 | Admin → Catalogue → upload hero/gallery images (presign → S3) |
| 2.4 | Supply: ≥1 verified pujari + `python scripts/sync_active_puja_pricing.py` |
| 2.5 | Customer visibility: `GET /v1/pujas?limit=50` (expect 22 active pujas after Hyderabad seed) |

**Source CSV (ops, not Admin UI):** `spec/catalog/hyderabad_launch_mdm.csv` via `bootstrap_catalog.py`.

**Blindspot:** Active puja without verified `pujari_pricing` is **hidden** from customer API — by design.

**Workflow:** No dedicated workflow yet; run manually after Phase 1 smoke passes. Optional follow-up: add `staging-catalog-bootstrap.yml` (dispatch only).

---

## Phase 2b — Staging nginx (HTTPS edge, OCI DNS)

**Staging only.** Production uses **NLB → uvicorn** without nginx (see edge policy above).

| Step | Action |
|------|--------|
| 2b.1 | OCI DNS **A record** `api-stg.<domain>` → `stg-aio-1` public IP |
| 2b.2 | Install nginx + TLS cert on **`stg-aio-1`**; proxy **`443` → `127.0.0.1:8000`** |
| 2b.3 | `curl -sS https://api-stg.<domain>/health/live` and `/health/ready` |
| 2b.4 | Set `KYC_REDIRECT_URL=https://api-stg.<domain>/v1/pujari/kyc/callback` before Phase 3 Setu register |

Repo artifacts (when added): `deploy/nginx/staging-api.conf`, `deploy/staging/install_nginx_tls.sh`. CI: **`deploy-staging` component `nginx_tls`** — see [`STAGING_NGINX_TLS.md`](./STAGING_NGINX_TLS.md).

---

## Phase 3 — KYC (Setu + redirect URL)

**Not Phase 2.** Catalogue Phase 2 is Postgres + **catalog** presign (`S3_BUCKET_CATALOG`). Partner KYC uses a **separate private bucket** (`S3_BUCKET_KYC`) configured in **Phase 1** — same `api.env` keys, verified by `verify_staging_storage.py` (catalog **and** kyc roundtrip).

| Flow | Uses OCI presigned URL? |
|------|-------------------------|
| **Setu DigiLocker** (redirect + callback) | **No** — HTTPS to Setu; API stores pulled docs in `S3_BUCKET_KYC` server-side |
| **Partner selfie** | **Yes** — `presign_kyc_put` → app PUT to KYC bucket (`partner_kyc_service`) |
| **Admin KYC queue view** | **Yes** — `presign_kyc_get` for stored proof objects |

**Before Setu dashboard work:** confirm Phase 1 strict smoke passed for **both** buckets. Optional E2E after Phase 3 env: partner onboarding selfie presign + confirm on staging.

| Variable | Staging value pattern |
|----------|----------------------|
| `KYC_REDIRECT_URL` | `https://<public-host>/v1/pujari/kyc/callback` (or `http://IP:8000/...` for sandbox only) |
| `KYC_SETU_*` | Same sandbox keys as dev |
| `KYC_IDENTITY_PEPPER` | Stable per DB; do not rotate without migration plan |
| `KYC_APP_RETURN_URL` | `managuruji://kyc/complete` |

Register **exact** `KYC_REDIRECT_URL` in Setu dashboard.

**Blindspot:** Nginx-only VM without proxy to FastAPI `/v1/pujari/kyc/callback` → Setu callback 404.

**Defer** separate micro-VM until you need TLS + stable domain; staging can use API public IP if Setu allows.

---

## Phase 4 — Payments (Razorpay test)

| Item | Action |
|------|--------|
| `RAZORPAY_*` | Same test keys as dev |
| Webhook | Razorpay dashboard → `https://api-stg.managuruji.in/v1/webhooks/razorpay` |
| `RAZORPAY_WEBHOOK_SECRET` | Must match dashboard |
| One-shot verify | On VM: `scripts/staging_razorpay_webhook_smoke.py` — real test card + Razorpay-delivered webhook (phone `+919811119999`) |

**Blindspot:** Webhook URL is **not** an env var — must be configured in Razorpay.

---

## Phase 5 — Firebase (optional for staging)

| Variable | Dev | Staging |
|----------|-----|---------|
| `FCM_SERVICE_ACCOUNT_PATH` | `secrets/firebase-service-account.json` | `/etc/mana-guruji/firebase-service-account.json` |

If missing: push **SKIPPED**; partner poll still works.

---

## Phase 6 — SMS / Maps / Panchangam (when testing those flows)

- SMS: `FAST2SMS_*`, `MSG91_ENABLED=false` until DLT  
- `GOOGLE_MAPS_API_KEY` when testing addresses  
- `PANCHANGAM_VENDOR_URL` only if engine runs on VM `:3001`

---

## GitHub workflow map

| Workflow | When | Phase |
|----------|------|-------|
| [`deploy-staging.yml`](../../.github/workflows/deploy-staging.yml) | Push `dev` | 0 — code + migrate + admin rebuild |
| [`staging-storage-smoke.yml`](../../.github/workflows/staging-storage-smoke.yml) | Manual | **1** — S3 verify |
| [`redis-ensure-staging.yml`](../../.github/workflows/redis-ensure-staging.yml) | Manual | 0 — Redis DB 0/1/2 |
| [`db-verify.yml`](../../.github/workflows/db-verify.yml) | Manual | 2+ — schema |
| [`ci.yml`](../../.github/workflows/ci.yml) | Push/PR | Repo gates (not live env) |

**Recommended after Phase 1:** run **Staging storage smoke** on every `api.env` S3 change.

---

## Dev / laptop parity checklist

When adding a new env var to staging `api.env`:

1. Add to `app/core/config.py` (if new) + `deploy/env/staging.api.env.example`  
2. Document in `ENV_STAGING_REFERENCE.md`  
3. Add placeholder to laptop `.env` / `.env.example` (no secrets in git)  
4. If object storage related: extend `verify_staging_storage.py` if needed  
5. PM CSV row under `STG-CFG-*`

---

## Suggested CSV status (update as you go)

| Task_ID | Task_Name | Status |
|---------|-----------|--------|
| STG-CFG-001 | OCI buckets catalog + KYC | **Completed** 2026-10-24 |
| STG-CFG-002 | api.env S3 block + API restart | **Completed** 2026-10-24 |
| STG-CFG-003 | `verify_staging_storage.py` + Actions smoke | **Completed** (VM); run `staging-storage-smoke.yml` for CI-006 |
| STG-CFG-004 | `bootstrap_catalog.py` on staging | Not Started |
| STG-CFG-005 | Admin catalogue image upload smoke | Not Started |
| STG-CFG-006 | KYC redirect + Setu sandbox | Not Started |
| STG-CFG-007 | Razorpay webhook staging URL | Not Started |

*Last updated: 2026-10-24*
