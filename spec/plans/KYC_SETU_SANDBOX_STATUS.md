# Setu sandbox — partner KYC + PAN sign-off

**Last updated:** 2026-11-01  
**Environment:** Setu **`dg-sandbox`** (`KYC_SETU_*` + `KYC_SETU_PAN_PRODUCT_ID` in `api.env`)  
**Related:** [`KYC_ONBOARDING.md`](./KYC_ONBOARDING.md) · [`IDENTITY_PHONE_AND_NAME.md`](./IDENTITY_PHONE_AND_NAME.md) · [`STAGING_CONFIG_ROLLOUT.md`](./STAGING_CONFIG_ROLLOUT.md) Phase 3

---

## Completed (code + laptop dev QA)

| Item | Evidence |
|------|----------|
| **Canonical phone at OTP** | Merged **`dev`** PR #7 (`puja_platform`); Flutter PR #1 — `+91` E.164; dedupe script |
| **Aadhaar name on user** | DigiLocker ingest sets `users.full_name` when placeholder; device: legal name not "New User" |
| **Setu DigiLocker (Aadhaar)** | Start → callback/poll → identity + address docs in KYC bucket; `kyc_identity_registry` |
| **Partner selfie** | Presign → **`PUT /v1/pujari/documents/{id}/upload`** (API proxy to S3/OCI) → confirm (EXIF strip); fixes mobile→OCI presigned PUT 400 |
| **Setu PAN verify (sandbox)** | `POST /v1/pujari/kyc/pan` + `verify_pan`; test PAN **`ABCDE1234A`** → `pan_status=operative`; consent **`reason`** ASCII-normalized for Setu |
| **Partner tax profile UI** | Entity type + PAN screen; snackbar "PAN on file" on success |
| **CD to staging VM** | Merge **`dev`** → Deploy staging (self-hosted) green; VM **`deploy-staging`** @ same SHA as **`origin/dev`** (`47007f9` after PR #7) |

**Not in scope for “sandbox complete”:** production Setu, real PAN on sandbox, Setu webhooks (Phase 2), `pan_enc` filing (Phase 3), bank verification.

---

## Pending (before staging/product sign-off)

| ID | Task | Owner / how |
|----|------|-------------|
| **STG-CFG-006** | Public **`KYC_REDIRECT_URL`** (HTTPS) + register in Setu dashboard; nginx proxy **`/v1/pujari/kyc/callback`** | [`STAGING_NGINX_TLS.md`](./STAGING_NGINX_TLS.md) · **`deploy-staging` `nginx_tls`** |
| **STG-KYC-001** | Repeat full partner onboarding on **staging API** + **new Flutter build** (`API_BASE_URL` staging HTTPS) | Device QA |
| **STG-KYC-002** | **Admin A-KYC:** approve identity, address, photo → `verification_status=verified` | Admin console |
| **STG-CFG-006b** | Optional: merge **`bug/staging-deploy-git-clarity`** — deploy log SHA + sync VM `dev` ref (ops clarity) | PR → **`dev`** |
| **STG-GATE** | MVP A–F + **`STG-S6`** ready health on staging | [`STAGING_PENDING_CHECKLIST.md`](./project_pm/STAGING_PENDING_CHECKLIST.md) |
| **Prod** | **`dev` → `main`** + prod Setu product IDs + real PAN verify | [`STG_TO_PROD_PIPELINE.md`](./STG_TO_PROD_PIPELINE.md) |

---

## Sandbox test data (operators)

| Input | Use |
|-------|-----|
| PAN **`ABCDE1234A`** | Setu sandbox **valid** |
| PAN **`ABCDE1234B`** | Setu sandbox **invalid** |
| Real personal PAN | **Not found** on sandbox (expected) |
| Consent `reason` | ≥20 chars, **ASCII** (no em dash `—`) |

---

## PM tracker rows

| Task_ID | Status (2026-11-01) |
|---------|------------------------|
| **STG-CFG-006** | **In Progress** — backend on VM; HTTPS callback + Setu dashboard pending |
| **STG-KYC-001** | **In Progress** — laptop dev PASS; staging device pending |
| **STG-KYC-002** | **Not Started** — admin approve path |
| **L-SPRINT-2-TDS-KYC-PAN** | **Completed** (code); sandbox QA done on laptop |

Update CSV: [`project_pm/Mana_Guruji_OCI_PM_Tracker_Staging.csv`](./project_pm/Mana_Guruji_OCI_PM_Tracker_Staging.csv).
