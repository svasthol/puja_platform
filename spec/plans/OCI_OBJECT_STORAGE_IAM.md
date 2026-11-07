# OCI Object Storage + IAM — catalog & KYC

**App code:** Same on dev, staging, prod (`catalog_media.py`, `kyc_storage.py`, `s3_boto.py`). Only **env** (bucket names, endpoint, keys) and **OCI policies** change per environment.

**Verify after any IAM or `api.env` S3 change:**

```bash
set -a && source /etc/mana-guruji/api.env && set +a
python scripts/verify_staging_storage.py --strict
```

---

## Staging (done — reference)

| Item | Value |
|------|--------|
| Compartment | `mana-guruji-staging` |
| Identity domain | **Default** (no extra domain) |
| Catalog bucket | `mana-guruji-stg-catalog` — **Public** (customer read via `S3_CATALOG_PUBLIC_URL`) |
| KYC bucket | `mana-guruji-stg-kyc` — **Private** |
| Public catalog read | Policy `S3AllowAccesstopublic` — `any-user` **read/inspect** catalog bucket only |
| API object access (KYC) | Policy `kyc-verification-policy` — see below |
| API identity | Customer secret key on IAM user (e.g. in **Administrators** for staging) |

**KYC-only policy statement (staging — validated 2026-10):**

```text
Allow group Administrators to manage objects in compartment mana-guruji-staging where all { target.bucket.name = 'mana-guruji-stg-kyc' }
```

Catalog **upload** (admin presign) also needs `manage objects` on `mana-guruji-stg-catalog` for the same API key (separate policy line or existing admin coverage). Storage smoke **catalog + kyc put/get OK** confirms both.

**Never:** `Allow user …` (OCI rejects it). **Never:** `any-user` on KYC bucket.

---

## Production — budget-friendly IAM pattern

Same **Default** identity domain; **separate compartment** `mana-guruji-production` (see [`OCI_COMPARTMENTS.md`](./OCI_COMPARTMENTS.md)). Do **not** reuse staging bucket names or staging-only policies.

### 1. Buckets (compartment `mana-guruji-production`)

| Bucket | Visibility | Name (example) |
|--------|------------|----------------|
| Catalog | Public read (if using `S3_CATALOG_PUBLIC_URL`) | `mana-guruji-prod-catalog` |
| KYC | **Private** | `mana-guruji-prod-kyc` |
| Backups (optional) | Private | `mana-guruji-prod-pg-backups` |

### 2. Dedicated API group (least privilege — not Administrators)

| Step | Action |
|------|--------|
| 1 | Default domain → **Create group** `mana-guruji-prod-api` |
| 2 | Create **IAM user** `mana-guruji-prod-api` (or service user) — **not** your personal admin user |
| 3 | Add user to `mana-guruji-prod-api` only |
| 4 | **Customer secret key** on that user → prod `api.env` `S3_ACCESS_KEY` / `S3_SECRET_KEY` |

### 3. Policies (compartment `mana-guruji-production`)

**Catalog — anonymous read (optional, same pattern as staging):**

```text
Allow any-user to inspect buckets in compartment mana-guruji-production where all { target.bucket.name = 'mana-guruji-prod-catalog' }

Allow any-user to read objects in compartment mana-guruji-production where all { target.bucket.name = 'mana-guruji-prod-catalog' }
```

**API — KYC only:**

```text
Allow group mana-guruji-prod-api to manage objects in compartment mana-guruji-production where all { target.bucket.name = 'mana-guruji-prod-kyc' }
```

**API — catalog upload (admin presign):**

```text
Allow group mana-guruji-prod-api to manage objects in compartment mana-guruji-production where all { target.bucket.name = 'mana-guruji-prod-catalog' }
```

Or one statement with `where any { target.bucket.name = '…-prod-catalog', target.bucket.name = '…-prod-kyc' }`.

### 4. Prod cutover checklist

- [ ] Terraform or manual buckets in **prod compartment**
- [ ] Policies above; **no** staging policy names reused
- [ ] `/etc/mana-guruji/api.env`: prod bucket names + compat endpoint + **prod** secret key
- [ ] `python scripts/verify_staging_storage.py --strict` on prod VM (script name is generic — reads env)
- [ ] GitHub prod workflow / manual gate before go-live ([`STG_TO_PROD_PIPELINE.md`](./STG_TO_PROD_PIPELINE.md) **PRD-P0-005**)

### 5. Later hardening (when budget allows)

- Dynamic group + **instance principal** on app VMs instead of long-lived customer secret keys on disk
- OCI Vault for `S3_SECRET_KEY` / Setu / Razorpay — not in plain `api.env` in git

---

## Presigned URLs

Not created in OCI Console. The API generates them at runtime using the customer secret key (or instance principal). IAM must allow **`manage objects`** on the target bucket for that identity.

| Flow | Bucket | Mechanism |
|------|--------|-----------|
| Admin catalog image | Catalog | `presign_catalog_put` |
| Partner selfie | KYC | `presign_kyc_put` |
| Admin KYC preview | KYC | `presign_kyc_get` |
| Setu Aadhaar files | KYC | `store_kyc_bytes` (server only) |

See [`STAGING_CONFIG_ROLLOUT.md`](./STAGING_CONFIG_ROLLOUT.md) Phase 1 & 3 · [`KYC_ONBOARDING.md`](./KYC_ONBOARDING.md).
