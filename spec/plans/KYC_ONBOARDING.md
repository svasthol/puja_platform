# Partner KYC onboarding — vendor-agnostic plan (DigiLocker first)

**Status:** PROPOSED — awaiting approval. No app code until sign-off.
**Owner track:** Phase 0.5 supply onboarding (`B-REGISTER`, `B-KYC`).
**Task status lives only in [`STATUS.md`](./STATUS.md)** — this file is scope/design, never a `Status:` source.

> **Why this doc exists:** `STATUS.md` chose **Setu DigiLocker** for `B-KYC`, but
> `PARTNER.md` / `API_CONTRACTS.md` still describe the old manual S3-upload flow. This plan
> aligns everything on a **vendor-agnostic KYC layer** (Setu is the first provider; swappable)
> and defines the exact files, endpoints, DB, security, and tests before implementation.

---

## 0. Non-negotiables inherited from `project.mdc` / `ARCHITECTURE.md`

- **Vendor calls live in a service, never in a route handler** (same rule as `sms_router.py`).
- **Admin still approves each document** — automated fetch never auto-flips `verification_status='verified'`
  (physical-safety gate, `SPEC_AMENDMENTS §19` / `ADMIN.md` A-KYC). The vendor only *populates* documents.
- **Never store raw secrets / raw Aadhaar / raw XML in DB or logs.** Files → private `S3_BUCKET_KYC`;
  DB keeps references + masked fields only. Structlog redaction mandatory.
- Python 3.12 · `async def` handlers · Pydantic v2 (`ConfigDict`) · SQLAlchemy 2.0 `Mapped[]` ·
  `psycopg` v3 · `httpx` (already pinned) · `structlog`. **No new dependency needed.**
- Migrations: new SQL file in `spec/db/`, chains after **019**; no colon-prefixed text.
- Workers (if used): sync `psycopg.connect`, own Redis lock, idempotent.

---

## 1. Design principle — plug-and-play vendor layer

The entire integration talks to **one interface**, not to Setu directly. Swapping Setu →
another vendor (Signzy, HyperVerge, Digitap…) means adding **one file** + flipping **one env var**.

```
              ┌─────────────────────────────────────────────┐
 route/       │  app/api/v1/endpoints/partner_onboarding.py  │  (thin; async; no vendor import)
 service      │  app/services/partner_kyc_service.py         │  (orchestration + DB + S3 + audit)
              └───────────────────────┬─────────────────────┘
                                      │ depends only on the Protocol
                          ┌───────────▼───────────┐
 vendor layer             │ app/services/kyc/      │
                          │   base.py  (Protocol)  │◄── contract every vendor implements
                          │   registry.py          │◄── get_kyc_vendor() reads KYC_VENDOR env
                          │   types.py             │◄── shared DTOs (no vendor shapes leak out)
                          │   setu_digilocker.py   │◄── Setu impl #1
                          │   (future) signzy.py   │
                          └────────────────────────┘
```

**Rule:** `partner_kyc_service.py` and the endpoint import **only** `kyc.registry` + `kyc.types`.
They must never `import setu_digilocker`. This is what makes the vendor swappable.

---

## 2. Directory & file layout (exact naming — additive only)

```
app/
  api/v1/endpoints/
    partner_onboarding.py         NEW  — /v1/pujari/register + /v1/pujari/kyc/*
    webhooks.py                   EDIT — add POST /webhooks/kyc/{vendor}
  services/
    kyc/                          NEW package
      __init__.py
      base.py                     KycVendor Protocol (create/status/fetch/verify_webhook)
      types.py                    DTOs: KycStartResult, KycStatusResult, KycIdentity, KycVendorError
      registry.py                 get_kyc_vendor() -> KycVendor  (env-driven singleton)
      setu_digilocker.py          Setu DigiLocker implementation (httpx)
    partner_kyc_service.py        NEW  — orchestration: DB rows, S3 ingest, doc creation, audit
    kyc_ingest.py                 NEW  — download vendor file_url -> S3 KYC bucket -> pujari_documents
    kyc_storage.py                REUSE (presign GET already exists) — add presign_kyc_put if selfie upload kept
  models/
    kyc.py                        NEW  — KycVerificationRequest ORM (SQLAlchemy 2.0 Mapped)
  schemas/
    partner_kyc.py                NEW  — request/response Pydantic v2 models
  core/
    config.py                     EDIT — add KYC_* settings block (see §5)
    kyc_config.py                 REUSE — REQUIRED_DOC_TYPES (may add mapping for vendor→doc_type)
  workers/
    kyc.py                        NEW (optional Phase 2) — async fetch/retry after webhook
spec/
  db/migration_020.sql            NEW  — kyc_verification_requests table (chains after 019)
migrations/versions/
  012_partner_kyc.py              NEW  — op.execute(open("spec/db/migration_020.sql").read())
tests/
  test_partner_register.py        NEW  — B-REGISTER
  test_partner_kyc_digilocker.py  NEW  — B-KYC vendor flow (mocked Setu httpx)
  test_kyc_vendor_registry.py     NEW  — registry swap + Protocol conformance
```

> Migration label note: alembic `versions/` currently ends at `011`; migrations 012–019 are
> applied via `spec/db/migration_0XX.sql` + apply scripts (see `STATUS.md` MIG rows). Follow the
> **same apply path as 018/019** for the new SQL file. Confirm 012-vs-020 numbering with the
> apply mechanism before writing (SQL file = `020`; alembic revision label continues its own chain).

---

## 3. Vendor contract (`app/services/kyc/base.py`)

Every vendor implements this Protocol. Nothing outside `kyc/` knows Setu exists.

```python
class KycVendor(Protocol):
    name: str  # e.g. "setu_digilocker"

    async def start_digilocker(self, *, redirect_url: str) -> KycStartResult: ...
    async def get_request_status(self, *, vendor_request_id: str) -> KycStatusResult: ...
    async def fetch_aadhaar(self, *, vendor_request_id: str) -> KycIdentity: ...
    # Phase 4 (PAN):
    async def verify_pan(self, *, pan: str, consent: bool, reason: str) -> KycPanResult: ...
    # Webhook (Phase 2):
    def verify_webhook_signature(self, *, raw_body: bytes, signature: str) -> bool: ...
    def parse_webhook(self, *, payload: dict) -> KycWebhookEvent: ...
```

**DTOs in `types.py`** normalize vendor JSON into platform shapes so the service never sees
Setu field names:
- `KycStartResult(vendor_request_id, redirect_or_kyc_url, status, expires_at)`
- `KycStatusResult(status, scope, error_code)` — status normalized to
  `created | authenticated | success | failed | expired`
- `KycIdentity(masked_aadhaar, name, dob, address, photo_bytes, xml_bytes)` — **transient**,
  handed straight to `kyc_ingest`; never persisted whole.
- `KycVendorError(code, message, retryable)` — raised on non-2xx; mapped to HTTP in the handler.

---

## 4. Data model (`spec/db/migration_020.sql`)

**Store the journey, not the identity.** Aadhaar files go to S3 + `pujari_documents`.

```sql
CREATE TABLE kyc_verification_requests (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pujari_id          UUID NOT NULL REFERENCES pujaris(id) ON DELETE CASCADE,
    vendor             VARCHAR(40)  NOT NULL,          -- 'setu_digilocker'
    kind               VARCHAR(20)  NOT NULL           -- 'digilocker' | 'pan'
                         CHECK (kind IN ('digilocker','pan')),
    vendor_request_id  VARCHAR(100) NOT NULL,
    status             VARCHAR(30)  NOT NULL DEFAULT 'created'
                         CHECK (status IN ('created','authenticated','success','failed','expired')),
    scope              VARCHAR(100),                   -- e.g. 'ADHAR', 'ADHAR+PANCR'
    error_code         VARCHAR(60),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at         TIMESTAMPTZ NOT NULL,
    UNIQUE (vendor, vendor_request_id)
);

-- one live (created/authenticated) request per pujari per kind — closes the double-start race
CREATE UNIQUE INDEX ux_kyc_one_live_request
    ON kyc_verification_requests (pujari_id, kind)
    WHERE status IN ('created','authenticated');
```

- **No `aadhaar_number` column.** Masked value (if ever needed) lives only in a document's metadata.
- `redirect_url` / `vendor_url` are **not** stored (they contain single-use tokens); the URL is
  returned to the client in the start response and discarded server-side.
- Migration must **not** DROP anything; append-only DDL.

---

## 5. Config (`app/core/config.py` — new block, mirrors SMS/Panchangam style)

```python
# ---- KYC / identity vendor (plug-and-play) -------------------------------
KYC_VENDOR: str = "setu_digilocker"          # switch vendor here (registry key)
KYC_REDIRECT_URL: str = ""                   # public HTTPS callback (staging/ngrok in dev)
KYC_REQUEST_TTL_MINUTES: int = 30
# Setu-specific (only read by setu_digilocker.py):
KYC_SETU_BASE_URL: str = "https://dg-sandbox.setu.co"   # prod: https://dg.setu.co
KYC_SETU_CLIENT_ID: str = ""
KYC_SETU_CLIENT_SECRET: str = ""
KYC_SETU_DIGILOCKER_PRODUCT_ID: str = ""
KYC_SETU_PAN_PRODUCT_ID: str = ""
KYC_SETU_WEBHOOK_SECRET: str = ""
```

- Secrets **only** via env / SSM / Doppler — never committed. Add placeholders to `.env.example`.
- `.env.example` addition + `STACK_VERSIONS.md` note (no version change since `httpx`/`boto3`
  already pinned) per the dependency-sync rule.

---

## 6. API contract (partner app)

All under `app_context=pujari` (`require_pujari`), except the webhook (public, signature-verified).

| Method & path | Purpose | Success |
|---|---|---|
| `POST /v1/pujari/register` | `{bio?, years_experience?}` → create `pujaris` row `pending` (idempotent per user) | 201 `{pujari_id, verification_status}` |
| `POST /v1/pujari/kyc/digilocker` | Start DigiLocker journey | 201 `{request_id, url, expires_at}` |
| `GET /v1/pujari/kyc/requests/{request_id}` | Poll journey status (owner only) | 200 `{status, scope, doc_types_created[]}` |
| `GET /v1/pujari/kyc/status` | Overall onboarding status | 200 `{verification_status, required:[{doc_type, status}]}` |
| `POST /v1/pujari/kyc/pan` *(Phase 4)* | `{pan, consent, reason}` standalone PAN | 200 `{verification, name?}` |
| `POST /v1/webhooks/kyc/{vendor}` | Vendor async callback (signature-verified) | 200 always once recorded |

**Deprecation:** the old `POST /v1/pujari/documents` (manual S3 presign) becomes **optional /
selfie-only** — kept only if we decide the Aadhaar photo does not satisfy the `photo` doc type
(see decision D1 in §11). Spec contract (`API_CONTRACTS.md`) updated at approval.

**Error mapping (via the shared exception handler — never a bare 500):**
| Cause | HTTP |
|---|---|
| `KycVendorError(retryable=false)` (e.g. bad request) | 422 |
| `KycVendorError(retryable=true)` / upstream 5xx/timeout | 502 |
| request not found / not owned | 404 |
| duplicate live request (`ux_kyc_one_live_request`) | 409 |
| vendor auth (401 from Setu → our misconfig) | 500 + ops alert (config error, not user) |

---

## 7. End-to-end flow (DigiLocker, backend-first)

```
Pujari (OTP-authed)          Backend                         Setu sandbox
      | register             |                               |
      |--------------------->| INSERT pujaris(pending)        |
      | start digilocker     |                               |
      |--------------------->| get_kyc_vendor().start_digilocker(redirect_url)
      |                      |------------------------------>| POST /api/digilocker/
      |                      |  INSERT kyc_verification_requests(created)
      | {url}                |<------------------------------|
      | open url (browser/WebView) --------------------------> consent journey
      |                      |   webhook OR redirect back     |
      |                      |<==============================| (Phase 2 webhook / Phase 1 poll)
      | poll status          |                               |
      |--------------------->| if authenticated:              |
      |                      |   vendor.fetch_aadhaar --------->| GET /api/digilocker/:id/aadhaar
      |                      |   kyc_ingest: XML/photo -> S3   |
      |                      |   INSERT pujari_documents(pending) x N
      |                      |   UPDATE request status=success |
      | {status, docs}       |<------------------------------|
      |                      |                               |
   Admin console: GET /v1/admin/kyc/pending → approve each → verification promoted (existing A-KYC)
```

**Phase 1 uses polling + redirect query params** (`?success=&id=&scope=`). **Webhook is Phase 2**
(async + signature). Both converge on the same `partner_kyc_service.finalize_request()` so there's
no duplicated ingest logic.

---

## 8. Security & compliance (no blind spots)

| Risk | Mitigation |
|---|---|
| Secret leakage | Env/SSM only; `.env.example` placeholders; **rotate the sandbox secret already shared in chat** |
| PII at rest | No Aadhaar number/XML in DB; files in private `S3_BUCKET_KYC` (SSE); short-lived presigned GET for admin |
| PII in logs | Structlog redaction: log `request_id`, `status`, `pujari_id`; **never** name/DOB/Aadhaar/photo |
| Webhook spoofing | `verify_webhook_signature` (HMAC-SHA256, `x-setu-signature`) before any DB write; invalid → 400 + `WEBHOOK_SIGNATURE_INVALID` alert (reuse Razorpay pattern) |
| Replay / double-fetch | Idempotent `finalize_request()` keyed on `vendor_request_id`; ingest is safe to run twice (version bump on `pujari_documents`, `is_current` swap) |
| Double-start race | `ux_kyc_one_live_request` partial unique index → 409 |
| Auto-verify bypass | Service only inserts `status='pending'` docs; promotion stays in A-KYC admin path |
| Request expiry | `expires_at`; expired requests rejected on poll; a sweep/worker may mark `expired` (Phase 2) |
| Vendor lock-in | Protocol + registry; DTOs hide Setu shapes; swap = new file + `KYC_VENDOR` env |
| Consent (PAN) | PAN calls require explicit `consent=Y` + ≥20-char `reason` (Setu contract); capture consent in UI + audit |

---

## 9. Testing strategy (must be green before Flutter)

- **`test_kyc_vendor_registry.py`** — `get_kyc_vendor()` returns the configured impl; a fake vendor
  satisfies the Protocol → proves swappability.
- **`test_partner_register.py`** — register creates pending pujari; second call idempotent; a
  non-pujari token is handled per auth rules.
- **`test_partner_kyc_digilocker.py`** — Setu HTTP **mocked** (respx/monkeypatch httpx):
  - start → row `created` + url returned
  - poll while `unauthenticated` → `created`
  - `authenticated` → fetch → S3 ingest (mocked) → N `pujari_documents(pending)` → status `success`
  - duplicate start → 409
  - vendor 5xx → 502, no partial rows (transaction rolls back)
  - webhook bad signature → 400; good → finalize once (idempotent on replay)
- **Manual sandbox E2E runbook** (documented in this plan's Appendix): real `999999990019` journey
  in a browser against `dg-sandbox.setu.co`, admin approves in console.
- All DB assertions inside `async with session.begin()`; follow existing `tests/` fixtures.

**Backend acceptance gate (from prior turn, restated):**
- [ ] register → pending pujari
- [ ] start returns valid sandbox url
- [ ] consent → status `authenticated`
- [ ] fetch → `pujari_documents(pending, is_current=true)`
- [ ] admin queue shows docs w/ presigned preview
- [ ] approve required set → `verification_status=verified`
- [ ] on promotion to `verified`, `ensure_partner_dispatch_readiness()` runs idempotently
      (service areas, default availability, catalogue pricing — `kyc_verification.py`)
- [ ] verified pujari can heartbeat + receive offers (requires readiness rows + online toggle)
- [ ] expired/revoked/5xx → clean error, no orphan rows
- [ ] pytest green (happy + failure modes)

---

## 10. Observability (aligns with `OBSERVABILITY.md` `kyc` component)

- Structlog events: `kyc_request_started`, `kyc_request_finalized`, `kyc_vendor_error`,
  `kyc_webhook_received`, `kyc_webhook_signature_invalid` (all PII-free).
- Reuse `M-HEALTH-KYC` pending-docs gauge (already planned). New requests naturally feed the
  existing admin queue → no new dashboard needed for v1.
- Ops alert on repeated `kyc_vendor_error(retryable=true)` spikes (Phase 2, optional).

---

## 11. Open decisions (resolve at approval — small, high-clarity)

| # | Decision | Recommended default |
|---|---|---|
| D1 | Does Aadhaar photo satisfy the `photo` doc type? | **Yes** for v1 (one less upload); revisit if compliance wants a live selfie |
| D2 | `identity_proof` + `address_proof` both from one Aadhaar pull? | **Yes** — two `pujari_documents` rows from the same fetch |
| D3 | Webhook in v1 or Phase 2? | **Poll + redirect** in v1; **webhook** in Phase 2 |
| D4 | PAN in onboarding v1? | **Optional skip** (spec = nullable PAN); nudge before payouts |
| D5 | Bank account (Setu BAV) | **Out of scope here** — Phase 3 + Razorpay Route |
| D6 | Migration SQL number vs alembic label | SQL = `migration_020.sql`; confirm alembic revision label with apply mechanism |

---

## 12. Task rows to add to `STATUS.md` (on approval — status added there, not here)

| ID | Replaces / relates | Scope |
|---|---|---|
| `B-REGISTER` | unblock (was HOLD) | `POST /v1/pujari/register` |
| `B-KYC-VENDOR` | supersedes S3-only `B-KYC` | vendor layer + `kyc_verification_requests` + start/status/ingest |
| `B-KYC-WEBHOOK` | new (Phase 2) | signed webhook + async finalize |
| `B-KYC-PAN` | new (Phase 4) | standalone PAN via vendor |
| `P-FLUTTER-REGISTER` | unblock after backend E2E | register screen |
| `P-FLUTTER-KYC` | unblock after backend E2E | DigiLocker WebView + status screen |

Spec files to amend at approval: `PARTNER.md` (B-KYC flow), `API_CONTRACTS.md` (new endpoints),
`SPEC_AMENDMENTS.md` (vendor-agnostic KYC section), `MOBILE_FLUTTER.md` (KYC screens), and this
file linked from `MASTER.md` Phase 0.5.

---

## 13. Rollout order (strict)

1. **Approve this plan** (+ resolve §11 decisions).
2. **Spec lock** — amend the files in §12 (docs only).
3. **Backend Phase 1** — vendor layer + register + start/status/ingest + migration 020 + tests.
4. **Manual sandbox E2E** — real DigiLocker test identity; admin approve.
5. **Backend Phase 2** — webhook + expiry sweep (optional but recommended before prod).
6. **Flutter** — register + DigiLocker WebView + status, aligned to the frozen contract.
7. **PAN (Phase 4)** — only after DigiLocker E2E is green.
8. **Production** — Setu Bridge prod creds + agreements, `KYC_SETU_BASE_URL=https://dg.setu.co`,
   `KYC_VENDOR` unchanged (proves the swap path already works via env).

---

## Appendix A — Manual sandbox runbook (dev, no code)

```powershell
# secrets from local .env, never inline
$h = @{
  "x-client-id"            = $env:KYC_SETU_CLIENT_ID
  "x-client-secret"        = $env:KYC_SETU_CLIENT_SECRET
  "x-product-instance-id"  = $env:KYC_SETU_DIGILOCKER_PRODUCT_ID
  "Content-Type"           = "application/json"
}
# 1) create
$r = Invoke-RestMethod -Method Post -Uri "https://dg-sandbox.setu.co/api/digilocker/" `
       -Headers $h -Body '{"redirectUrl":"https://<public-https>/kyc/callback"}'
$r    # -> id, status=unauthenticated, url   (open url in browser, use test Aadhaar 999999990019)
# 2) status
Invoke-RestMethod -Method Get -Uri "https://dg-sandbox.setu.co/api/digilocker/$($r.id)/status" -Headers $h
# 3) aadhaar (after authenticated)
Invoke-RestMethod -Method Get -Uri "https://dg-sandbox.setu.co/api/digilocker/$($r.id)/aadhaar" -Headers $h
```

Docs: DigiLocker quickstart (`docs.setu.co/data/digilocker/quickstart`),
PAN quickstart (`docs.setu.co/data/pan/quickstart`).
