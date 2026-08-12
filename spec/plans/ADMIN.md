# Admin portal — backend + Next.js track

Tasks trace to `spec/API_CONTRACTS.md` §Admin, `DISPATCH_FLOW.md` admin flows, and
`SPEC_AMENDMENTS.md` §19 (Phase 4 control plane).

**Phase 4 ≠ go-live.** Phase 4 lets ops run the marketplace without engineering or SQL.
**Go-live with real money** still requires Phase 3 (`P-RAZORPAY-ROUTE`, `P-SPLITS`,
`P-PAYOUT`, CA memo). See `MASTER.md` §Phase 4.

**Phase 3 ON HOLD:** Money automation tasks stay `BLOCKED`. Phase 4 may proceed in parallel.

> **Status lives in `STATUS.md` — the single source of truth for implementation progress.**
> Track files define scope only: Spec / Files / Acceptance / Depends-on. Never add a
> `Status:` field here; it will drift.

---

## Sprint 4-0 — Security hotfix (ship before any admin surface)

**Five tasks + migration 009** — all block every admin endpoint and fix auth bugs affecting
all apps. `P-ADMIN-ROLE` + `P-ADMIN-AUTH` + `P-ADMIN-AUTH-FIX` share `auth.py`; `P-AUTH-FIX`
fixes refresh/logout + OTP lockout for customer/pujari too; `P-ADMIN-SEED` supplies the
role rows they check.

**Migration 009 ships in this sprint** (not 4A): `P-AUTH-FIX` needs `refresh_jti`,
`P-ADMIN-SEED` needs the `roles` seed, `P-ADMIN-AUTH` needs `admin_credentials`. The rest
of 009's scope (audit table, `revoked` status, promo CHECK) is inert until 4A/4C uses it —
shipping it early costs nothing.

**Build order:** `P-ADMIN-AUTH-FIX` (no migration needed — closes the live hole first) →
migration 009 → `P-AUTH-FIX` → `P-ADMIN-SEED` → `P-ADMIN-ROLE` → `P-ADMIN-AUTH`.
SEED before ROLE: role rows must exist before anything checks them.

### P-ADMIN-AUTH-FIX — Close admin OTP escalation (query param)
- **Spec:** SPEC_AMENDMENTS.md §19.1; `API_CONTRACTS.md` §Auth
- **Priority:** **P0**
- **Files:** `app/schemas/auth.py`, `app/api/v1/endpoints/auth.py`
- **Problem:** `otp_verify(..., app_context: str = "customer")` is a FastAPI **query param**.
  Any phone that passes OTP can call `?app_context=admin` — no role check; user auto-created
  if missing; claim appears in proxy/access logs.
- **Acceptance:** `app_context` moves to **`OtpVerify` body** (`customer` | `pujari` only on
  SMS path). Admin never uses SMS OTP (`P-ADMIN-AUTH`). Reject unknown contexts at schema layer.

### P-AUTH-FIX — Refresh/logout + OTP attempt persistence
- **Spec:** SPEC_AMENDMENTS.md §19.1
- **Priority:** **P0** (all apps — not admin-specific)
- **Files:** `app/api/v1/endpoints/auth.py`, `app/core/security.py`, migration **009**
- **Problem (verified):**
  1. `refresh` / `logout` compare `refresh_token_hash == hash_secret(token)` — bcrypt with
     `gensalt()` never matches. Use JWT `jti` lookup + `verify_secret` (see `security.py`).
  2. Failed OTP increments `attempts` then raises inside `get_db_txn` → rollback discards count.
- **Acceptance:**
  - Add `refresh_jti` (UNIQUE) on `auth_sessions`; lookup by `jti`, verify hash on use.
  - OTP failures persist (Redis per-phone/row counter or autonomous write outside verify txn).
  - Integration tests for refresh rotation, logout, 5th failed OTP.

### P-ADMIN-ROLE — Admin role enforcement (platform)
- **Spec:** SPEC_AMENDMENTS.md §8, §19; `API_CONTRACTS.md` §Auth
- **Priority:** **P0 hotfix** (not deferred to Sprint 4A)
- **Files:** `app/core/dependencies.py`, `app/api/v1/endpoints/auth.py`
- **Acceptance (both halves required):**
  1. **Issuance:** `POST /v1/auth/otp/verify` with `app_context=admin` → **403** unless
     `user_roles` contains `admin` or `support`. Never mint admin tokens for arbitrary OTP users.
  2. **Dependency:** `require_admin` loads `user_roles` from DB; populates `Principal.roles`;
     rejects tokens without `admin` or `support`. JWT `app_context` alone is insufficient.
- **Why now:** `A-ADVANCE` is live; current code trusts client-asserted `app_context=admin`.

### P-ADMIN-SEED — Roles seed + first-admin bootstrap
- **Spec:** SPEC_AMENDMENTS.md §19
- **Priority:** **P0** (P-ADMIN-ROLE checks roles that are never seeded)
- **Problem:** `seed.sql` seeds only `status_types`. The `roles` table has **no rows** —
  `user_roles` lookups can never match. And role assignment is admin-only, so the first
  admin cannot be created through the API (chicken-and-egg).
- **Acceptance:**
  - Migration 009 seeds `roles`: `('admin')`, `('support')` (idempotent `ON CONFLICT`)
  - First admin bootstrap: documented one-time script (`scripts/`) or migration-time
    INSERT into `user_roles` keyed by env-provided phone — never a hardcoded UUID
  - `POST /v1/admin/users/{id}/roles` (admin-only) for subsequent assignments
  - **First-login TOTP enrolment (closes the bootstrap lockout):** the bootstrap gives the
    first admin a role but no credential — and enrolment normally requires being logged in.
    (Magic-link can't rescue this either: `users.email` is nullable and the OTP signup path
    sets it to `None`.) **Rule:** a user who **has** an admin/support role but **no**
    `admin_credentials` row may **self-enrol TOTP exactly once** on first admin login
    (server generates the secret, returns the provisioning URI/QR, requires a valid TOTP
    code to activate). Safe because roles only come from the bootstrap or an existing
    admin. This also covers every future admin, not just the first. After activation,
    re-enrolment requires an existing admin to reset the credential.
- **IMPLEMENTED (Sprint 4-0) — deviation: admin-vouched, not phone-only self-enrol.**
  Phone-only self-enrol has a race: anyone who knows a new admin's phone can bind their
  own authenticator in the window between role-assignment and the real admin's first login.
  Shipped instead (strictly more secure, still SMS-free):
  - **First admin:** `scripts/bootstrap_admin.py` (env-keyed `ADMIN_PHONE`) promotes the
    user to `admin` **and** provisions their TOTP secret in one step — zero enrol window.
  - **Every other admin:** an existing admin provisions/resets via
    `POST /v1/admin/users/{id}/credential` (returns the `otpauth://` URI + secret once).
    The target must already hold an admin/support role (409 otherwise).
  - **Activation:** the first successful `POST /v1/admin/auth/login` (valid TOTP code) sets
    `activated_at`. `last_used_step` blocks same-code replay (strictly-increasing step).
  There is no phone-only self-enrol endpoint. TOTP is stdlib RFC 6238 (`app/core/totp.py`,
  validated against the RFC test vectors) — no `pyotp` dependency.

### P-ADMIN-AUTH — Admin login without SMS OTP
- **Spec:** SPEC_AMENDMENTS.md §19
- **Priority:** **P0** (Phase 4 exit gate depends on it)
- **Files:** `app/api/v1/endpoints/auth.py`, `app/core/config.py`
- **Problem:** the only auth path is SMS OTP, and `P-SMS-DLT` is BLOCKED — without DLT,
  no admin can log into a production admin panel. `DEBUG=true` + `otp_dev_only` is dev-only.
  Admins are a small fixed set of employees; SMS OTP is the wrong mechanism for an internal
  console regardless of DLT.
- **Acceptance:**
  - **TOTP** (authenticator app) or **email magic-link** login path for `app_context=admin`,
    restricted to users with `user_roles` admin/support (reuses P-ADMIN-ROLE check)
  - TOTP secret / magic-link token storage needs a migration-009 table (e.g. `admin_credentials`)
  - **TOTP secrets cannot be hashed** — verification needs the plaintext. Store them
    **encrypted at the application layer** (AES-GCM / Fernet with a dedicated
    `TOTP_ENC_KEY` from the secrets manager — never `SECRET_KEY`, never plaintext in
    Postgres, never in `users`). Decide key sourcing (env/SSM) **before** writing
    migration 009. Magic-link tokens are single-use + short-lived → hash those like OTPs.
  - **Per-context token TTL:** admin refresh token ≤ **1 day** (customer/pujari keep 30 days).
    `ACCESS_TOKEN_EXPIRE_MINUTES` / `REFRESH_TOKEN_EXPIRE_DAYS` become per-`app_context`.
  - Removes the DLT dependency from Phase 4 entirely
- **IMPLEMENTED (Sprint 4-0):**
  - `POST /v1/admin/auth/login {phone, code}` in `app/api/v1/endpoints/admin_auth.py` — the
    **only** issuance path for an `app_context=admin` token. Gate: user is active **and**
    holds an admin/support role **and** presents a valid TOTP for an `admin_credentials` row.
    Every failure returns an identical generic 401 (no account enumeration); a rotated-out
    encryption key returns 503 (ops page), not 401.
  - Secrets stored as **Fernet** ciphertext (`app/core/crypto.py`) keyed by `TOTP_ENC_KEYS`
    (comma-separated for rotation: first encrypts, all decrypt; `key_version` on the row).
    Key sourcing = env var now (`TOTP_ENC_KEYS`), SSM/secrets-manager later — no schema change.
  - Per-context TTL in `app/core/security.py` (`access_ttl_minutes` / `refresh_ttl_days`):
    admin access = `ADMIN_ACCESS_TOKEN_EXPIRE_MINUTES` (30), admin refresh =
    `ADMIN_REFRESH_TOKEN_EXPIRE_DAYS` (1). `_issue_token_pair` sets the session `expires_at`
    from the same resolver, so token and session row never disagree.
  - Brute-force guard: `ADMIN_LOGIN_RATE_LIMIT_PER_HOUR` per phone (Redis).

---

## Auth & audit (Sprint 4A)

### A-AUDIT-LOG — Admin audit trail
- **Spec:** SPEC_AMENDMENTS.md §19; migration **009** (`admin_audit_log`)
- **Acceptance:**
  - Append-only table: `actor_user_id`, `action`, `entity_type`, `entity_id`, `before_json`,
    `after_json`, `change_reason`, `ip`, `created_at`
  - **Grant (migration 009):** `REVOKE UPDATE, DELETE ON admin_audit_log FROM puja_app` —
    the default `puja_app` grant includes UPDATE, so "no DELETE" alone is **not** append-only
    (same pattern as `REVOKE INSERT ON tax_statutory_config`)
  - **Ordering trap:** migrations run once per DB. If the guard skips the REVOKE because
    `puja_app` doesn't exist yet (dev runs as `postgres`), and prod creates the role *after*
    009 has run, the REVOKE never applies and nothing alarms. Therefore: `puja_app` creation
    is a **documented prerequisite of 009 in the prod runbook**, AND grants live in an
    **idempotent `scripts/apply_grants.sql`** run on every deploy — the migration guard is
    only a dev convenience, never the mechanism prod relies on.
  - **Writes:** every **successful** admin mutation logs a row in the same transaction
  - **Failed attempts:** logged out-of-transaction via structlog (a rejected reassign rolls
    back its audit row too — the DB row records outcomes, structlog records attempts)
  - **Reads:** PII lookups (`A-SEARCH` by phone) log `action=read` (DPDP)
- **4A scope (COMPLETED):** mutation audit wired on advance amount, role assign/revoke,
  TOTP credential provision (`app/services/audit.py` + `test_sprint40_admin.py`).
- **4C tail:** PII-read rows ship with `A-SEARCH` (Sprint 4C) — no 4B blocker.

### A-ADMIN-UI — Next.js admin shell
- **Spec:** `project.mdc` (Next.js 15 + TanStack Query + Zod)
- **Location:** `admin_ui/` at repo root (NOT inside `app/`)
- **Acceptance:**
  - Auth login via P-ADMIN-AUTH (TOTP/magic-link — not SMS OTP), layout, role-gated nav
  - Audit on mutations
  - `ALLOWED_ORIGINS` includes the production admin origin (default is `localhost:3000` only)
- **IMPLEMENTED (Sprint 4A):**
  - `admin_ui/` — Next.js 15.1 + React 19 + TanStack Query 5 + Zod 3 + Tailwind 3
  - `GET /v1/admin/me` for accurate RBAC nav (roles from DB, not JWT)
  - Screens: TOTP login, overview, advance amount, team roles, TOTP credential provision
  - Placeholder nav for 4B/4C (catalogue, KYC, bookings, promos)
  - See `admin_ui/README.md` for run instructions

**Sprint 4A closure (2026-07-19):** core deliverables above are shipped and manually
verified (TOTP login, roles, advance). Two items from the original 4A brief are
**re-homed to Sprint 4C** — not blockers for 4B:
- Support refund-cap **enforcement** → `A-REFUND` (policy: support capped per action +
  per day; admin uncapped; `P-REFUND-CAP` trigger already ✅)
- PII-read audit → `A-SEARCH` + `A-AUDIT-LOG` `action=read`

---

## Catalogue & pricing (Sprint 4B)

Normative data model: `pujas`, `puja_categories`, `puja_addons`, `pujari_pricing` in
`schema.sql`. Customer read APIs exist (`C-PUJAS`); admin write APIs are new.

### A-CAT-CATEGORIES — Puja categories
- **Spec:** SPEC_AMENDMENTS.md §20; `API_CONTRACTS.md` §Admin catalogue
- **Acceptance:**
  - `GET/POST/PUT /v1/admin/catalog/categories` — soft-disable via `is_active`; no hard DELETE
  - Fields (post–migration 011): `slug` (immutable), `description`, `display_order`, `image_media_id`
  - `PATCH /reorder` — single transaction replace ordered id list (Stage 3)
- **Wave-0 baseline shipped:** categories CRUD + UI (pre–011 fields only); extend after migration 011

### A-CAT-PUJAS — Puja CRUD
- **Spec:** §20; `DATABASE.md` duration snapshotted at booking
- **Depends on:** migration **011** (§20.1); **`pricing_resolver`** wired (§20.3) before pricing admin UI
- **Acceptance:**
  - `GET/POST/PUT /v1/admin/catalog/pujas` — name, description, duration, `default_price`,
    `price_max`, `tagline`, `slug`, `display_order`, category, `is_active`, `hero_media_id`
  - `GET /v1/admin/catalog/pujas/{id}/impact` — active unreleased holds + future bookings count
    (duration-increase + **price-change** warnings per §20.4 hold snapshot boundary)
  - Duration changes do not reshape existing bookings (snapshotted at insert)
  - **Duration-increase warning:** `slot_holds` are points (no duration); raising duration can
    make in-flight holds mutually incompatible → paid customer hits exclusion violation →
    auto-refund. UI must warn and show the count of active holds/bookings for that puja.
  - **Price-change warning:** quote/booking use live resolver until `C-HOLD` snapshots price on hold

### A-CAT-ADDONS — Puja addons
- **Spec:** §20
- **Acceptance:** `GET/POST/PUT /v1/admin/catalog/pujas/{id}/addons` — `description`, `display_order`

### A-CAT-CONTENT — Puja content items (inclusions, FAQ, etc.)
- **Spec:** §20.1 `puja_content_items`
- **Acceptance:** `PUT /v1/admin/catalog/pujas/{id}/content` — replace-all per `kind` (B-AVAIL pattern)

### A-CAT-MEDIA — Catalogue media pipeline
- **Spec:** §20.2
- **Acceptance:** `POST` presign + `POST .../confirm` (S3 HEAD); `upload_status` pending→ready;
  customer APIs only `ready` rows; public CDN URL via `S3_CATALOG_PUBLIC_URL`

### A-PUJARI-PRICING — Per-pujari price matrix
- **Spec:** §20.3; dispatch uses `pujari_pricing` (never `pujari_pujas`)
- **Gate:** **`pricing_resolver` must be wired** before this admin UI ships
- **Acceptance:** `GET/PUT /v1/admin/pujaris/{id}/pricing` — upsert `base_price` per `puja_id`

### A-AREAS — Service areas
- **Spec:** API_CONTRACTS.md; §19; **§21.3** (launch area dropdown)
- **Acceptance:**
  - CRUD `service_areas`, assign `pujari_service_areas`
  - Customer `GET /v1/service-areas` reads active zones (Kukatpally, LB Nagar, …)
  - **Launch:** area on address is **display-only** on offers; dispatch remains citywide
  - **Deactivation guard** — no direct booking→area link exists in the schema
    (`service_areas.pincode` is nullable, so address-pincode matching is unreliable).
    Guard path is therefore: `service_areas → pujari_service_areas → pujaris → active
    bookings` (non-terminal status). Block `is_active=false` when count > 0, or require
    explicit confirm showing the count — prevents silent `failed_no_pujari` cascades.

### A-RM — Relationship managers (launch §21.4)
- **Spec:** API_CONTRACTS.md; `SPEC_AMENDMENTS.md` §21.4
- **Acceptance:**
  - `GET/POST/PUT /v1/admin/relationship-managers` — name, phone, `is_active`, optional `city`
  - Default RM via `platform_settings` or per-booking assign (migration 012)
  - After booking confirm: customer and pujari see RM — **no** direct phone exchange
  - Phase 2: call masking (Exotel) may supplement RM at scale

---

## Settings

### A-ADVANCE — Advance booking amount
- **Spec:** API_CONTRACTS.md
- **Files:** `app/api/v1/endpoints/admin.py`

### A-TAX-CONFIG — Versioned tax configuration (commercial only)
- **Spec:** SPEC_AMENDMENTS.md §16; `A-TAX-CONFIG.md`; migration **007** (schema)
- **Scope gate:** **read UI in Phase 4**; **commercial POST blocked until CA memo seeds statutory rows**
- **Files:** `app/api/v1/endpoints/admin_tax.py`, `app/services/tax_config_service.py`
- **Supersedes:** A-COMMISSION (never `platform_settings` commission/gst)
- **Acceptance:**
  - `GET /v1/admin/tax-config/current` — commercial + statutory (read-only) + tax preview
  - `POST /v1/admin/tax-config/commercial` — only price fields; statutory keys → 422
  - Mandatory `change_reason`; append-only; no UPDATE/DELETE
- **Depends on:** P-ADMIN-ROLE (**P0**), migration 007 DDL applied

### A-PROMO — Promo CRUD
- **Spec:** API_CONTRACTS.md; §19
- **Acceptance:**
  - CRUD `promo_codes`
  - `valid_until > valid_from` enforced **both** in migration 009 (`CHECK`, matching the
    `ads` table pattern) **and** in the handler for a clean 422 — app validation is never
    the only line of defense (project.mdc rule 1)

---

## Supply (Phase 0.5 overlap — Sprint 4B)

### A-KYC — KYC review queue
- **Spec:** API_CONTRACTS.md §Admin KYC; SPEC_AMENDMENTS.md §19
- **Model (document-level approve; pujari verified only when the required set is complete):**
  - **Required `doc_type` set** defined as a constant/config (e.g. `identity_proof`,
    `address_proof`, `photo`) — `pujari_documents.doc_type` is free-text VARCHAR(30),
    so the required set lives in app config, not the schema
  - `POST /v1/admin/kyc/{doc_id}/approve|reject` acts on **the document row only**
  - `pujaris.verification_status = 'verified'` is promoted **only** when every required
    `doc_type` has an `is_current = true, status = 'verified'` row — never on a single doc
  - A rejection of any required current doc demotes/blocks promotion
- **Acceptance:**
  - `GET /v1/admin/kyc/pending` — pending `pujari_documents` **filtered `is_current = true`**
    (superseded versions never appear in the queue)
  - Signed URLs for private bucket docs only; show `pan_status` when available
  - **Role:** approve/reject = `admin` only — identity verification decides who enters
    customers' homes; `support` may view and recommend (see RBAC matrix)
- **Depends on:** B-KYC; S3 bucket configured (`S3_BUCKET_KYC`)
- **Priority:** Cannot onboard real supply without this

### A-PUJARI-SEARCH — Partner directory
- **Spec:** §19
- **Acceptance:** Search by phone, name, verification status, service area (cursor paginated)

---

## Operations (Sprint 4C)

**Sprint 4C closure (2026-07-22):** shipped and manually verified — booking search/detail,
manual reassign, refund override, promo CRUD, dispute (`in_progress` → `disputed`), money
read-only settlement card. Automated: `test_admin_slice2.py`, `test_admin_slice3.py`.
Status: **COMPLETED** in `STATUS.md`.

### A-SEARCH — Booking search
- **Spec:** API_CONTRACTS.md; §19 (audit read)
- **Acceptance:** Search by phone, booking id, date range, status — logs `A-AUDIT-LOG` read

### A-BOOKING-DETAIL — Booking 360°
- **Spec:** §19; mirrors `C-GET` + admin fields
- **Acceptance:** Status history, assignments, payment, refunds, dispatch state, address

### A-REASSIGN — Manual reassign
- **Spec:** DISPATCH_FLOW.md §Manual reassign; SPEC_AMENDMENTS.md §19
- **Depends on:** migration 009 (`('assignment','revoked')` status seed); `P-EXC-ADMIN-PATHS`
- **Acceptance:** Clear-revoke-insert in **ONE** transaction:
  1. `pujari_id = NULL`, `intended_pujari_id = NULL` + history (`changed_by` = admin)
  2. **Revoke the old pujari's accepted row:** flip it to `('assignment','revoked')`.
     Without this the booking keeps **two `accepted` assignments** forever
     (`ux_booking_assignments_one_live` can't catch it — both rows are resolved).
     **Never reuse `rejected`** — that records the old pujari as refusing work they
     accepted and poisons future reliability scoring. Safe with trigger 3: the update
     sets a non-accepted status, so the trigger body is skipped entirely.
  3. INSERT assignment: status `accepted`, **`expires_at = now() + interval '5 minutes'`**
     (Guard 1 rejects `expires_at <= now()` on INSERT — do not use `now()`),
     **`responded_at = now()`** (leaves `ux_booking_assignments_one_live` clean)
  4. Trigger 3 writes new pujari + confirmed history
- **Policy:** **Block** reassign when booking is `in_progress` or terminal — use `A-DISPUTE`
- **Errors:** `ex_bookings_pujari_no_overlap` → admin copy: *"Target pujari has an overlapping booking."*
- **Verify:** `LG-manual-reassign` — must assert exactly **one** `accepted` assignment per
  booking after reassign, and the old row is `revoked`

### A-REFUND — Refund ops
- **Spec:** API_CONTRACTS.md
- **Acceptance:**
  - `POST /v1/admin/refunds/override` — insert `refunds` `reason='admin_override'` (never inline Razorpay)
  - `GET /v1/admin/refunds?status=failed_permanent`
  - **`support` role:** capped override amount per action + per day; **`admin`** uncapped
- **Depends on:** P-REFUND-CAP; `P-EXC-ADMIN-PATHS`

### A-DISPUTE — Dispute resolution
- **Spec:** API_CONTRACTS.md, DISPATCH_FLOW.md disputed state
- **Acceptance:** `in_progress` → `disputed`; offline non-payment cases; no Razorpay refund for offline portion

### A-MONEY-READ — Settlement read-only (pre–Phase 3)
- **Spec:** §19
- **Acceptance:**
  - Show `payments.amount`, refund status per booking
  - Label: **"Collected online — settlement pending"** — never **"earnings"** until `P-SPLITS`
  - No payout actions until Phase 3 unblocked

---

## Auth (admin track mirror)

### A-ADMIN-ROLE — Role enforcement (admin track)
- **Spec:** SPEC_AMENDMENTS.md §8
- **Priority:** **P0** (same as `P-ADMIN-ROLE`)
- **Depends on:** Sprint 4-0 hotfix shipped

---

## RBAC matrix

| Action | `admin` | `support` |
|---|---|---|
| Catalogue CRUD | ✅ | ❌ (read-only optional) |
| KYC **view / recommend** | ✅ | ✅ |
| KYC **approve / reject** | ✅ | ❌ — identity verification gates entry into customers' homes |
| Booking search / dispute | ✅ | ✅ |
| Manual reassign | ✅ | ✅ (always audited — collusion vector) |
| Refund override | ✅ uncapped | ✅ capped per action + per day |
| Promo CRUD | ✅ | ❌ |
| Tax commercial POST | ✅ (post-CA) | ❌ |
| Advance amount PUT | ✅ | ❌ |
| Assign roles | ✅ | ❌ |

---

## Admin track exit gate

Phase 4 **COMPLETED** when ops can run the marketplace **without engineering or SQL**:

- [x] Sprint 4-0: `P-ADMIN-AUTH-FIX` — `app_context` in body; no admin via SMS OTP query param
- [x] Sprint 4-0: `P-AUTH-FIX` — refresh/logout jti lookup; OTP lockout persists
- [x] Sprint 4-0: `P-ADMIN-ROLE` hotfix shipped (issuance + dependency)
- [x] Sprint 4-0: `P-ADMIN-SEED` — roles + first-admin bootstrap
- [x] Sprint 4-0: `P-ADMIN-AUTH` — admin login works in production without SMS/DLT; admin refresh TTL ≤ 1 day
- [x] Sprint 4A (core): Next.js admin shell + CORS + mutation audit on live admin endpoints
- [x] Sprint 4A tail (closes in 4C): PII-read audit on search; support refund-cap on override
- [ ] Approve pujari end-to-end (KYC)
- [ ] Create/edit puja + category from admin UI
- [ ] Set pujari-specific puja price (`pujari_pricing`)
- [ ] Change advance amount → next quote reflects it
- [x] Find booking + manual reassign (`LG-manual-reassign` green)
- [ ] Resolve one `failed_permanent` refund
- [x] Create promo code with valid date range
- [x] Admin mutations + PII reads appear in `admin_audit_log`
- [ ] Tax config screen exists; commercial write gated until CA (Phase 3)

**Not required for Phase 4 exit:** live pujari payouts, checkout commission snapshot, `B-EARNINGS`.
