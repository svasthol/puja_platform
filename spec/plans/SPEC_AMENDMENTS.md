# Spec amendments — v3.2 (approved for development)

This document records additions to the v3 go-live spec from architecture review
(July 2026). Items here are **approved** and have been merged into the normative
spec files where noted. Implementation status is in `plans/STATUS.md`.

**Dispatch v2 (§21.6.A–H, July 2026):** immediate dispatch on payment, frozen `booking_class`,
dual partner UX (instant modal / advance inbox), sibling-offer supersede on accept, and night 2a
block are **approved** and specified in §21.6 below. DDL is migration **014**; backend task is
`P-LAUNCH-DISPATCH-V2` (PENDING in `plans/STATUS.md`).

---

## 1. Customer booking list

**Added to:** `API_CONTRACTS.md`

- `GET /v1/bookings` — cursor-paginated list of the authenticated customer's
  bookings (newest first). Required for order history in the customer app.

---

## 2. Refund sum cap (money safety)

**Added to:** `DATABASE.md` migration 005; `spec/db/migration_005.sql`

**Problem:** `ux_refunds_one_active_per_payment` prevents two *concurrent* active
refunds but not sequential succeeded refunds summing above `payments.amount`
(e.g. `late_payment` auto-refund succeeded, then `admin_override`).

**Rule:** Before inserting a refund, enforce:

```
SUM(amount) WHERE payment_id = ? AND status = 'succeeded' + new.amount <= payments.amount
```

Implement as DB trigger `trg_refunds_cap_total` or shared service guard.

---

## 3. Pujari cancel + provider dropout

**Added to:** `API_CONTRACTS.md`, `DISPATCH_FLOW.md`

**Problem:** Bookings scheduled days/weeks ahead can sit in `confirmed` if the
assigned pujari becomes unavailable or no-shows. Only customer cancel existed.

**New endpoint:**

- `POST /v1/bookings/{id}/pujari-cancel` — assigned pujari only; booking must be
  `confirmed` (not `in_progress`). One transaction: clear assignment per policy,
  customer notification, optional partial refund per cancellation policy,
  reliability penalty on pujari (future: rating/reliability score).

**Sweep extension (P-SWEEP-CONFIRMED):**

- Bookings `confirmed` past `scheduled_time + grace` (e.g. 90 min) without
  `in_progress` → alert ops + optional auto `disputed` or customer full refund
  of `amount_due_online` per launch policy.

**Launch priority:** Required for far-future bookings; deferrable for same-day-only MVP.

---

## 4. Pre-event reconfirmation

**Added to:** `DISPATCH_FLOW.md`

**Launch policy (July 2026):** **Mandatory** for advance bookings — see
`SPEC_AMENDMENTS.md` §21.7. §4 below is the baseline; §21 supersedes the
“optional launch / post-MVP” wording.

For bookings where `scheduled_date - today() > 1 day` (or ≥24h lead per §21):

- 24h before event: FCM/SMS to assigned pujari — confirm or cancel
- No response within 4h: enqueue admin alert; RM escalation (§21.7)

**Status:** **Mandatory at launch** for advance scheduling (§21.7).

---

## 5. Partner onboarding endpoints

**Added to:** `API_CONTRACTS.md`

- `POST /v1/pujari/register` — create pujari profile (`verification_status='pending'`)
- `POST /v1/me/devices` — register FCM `device_token`
- `POST /v1/pujari/documents` — KYC upload (signed S3 URL flow)

---

## 6. Address CRUD + geom invariant

**Added to:** `API_CONTRACTS.md`, `DATABASE.md` migration 005

- `POST/GET/PUT /v1/addresses` — customer addresses
- **Invariant:** every address write MUST set `geom` from lat/lng (app or trigger
  `trg_addresses_geom_sync`). Checkout already rejects `geom IS NULL` (422).

---

## 7. Dispatch eligibility — `pujari_pricing` (correction)

**Corrected in:** `DISPATCH_FLOW.md`

Eligibility step 3 previously said "specialization matches the puja." Schema uses:

- `pujari_pricing (pujari_id, puja_id)` — **primary filter** for "can perform this puja"
- `pujari_specializations` — optional broader skill tags; not sufficient alone

Plans must **not** reference `pujari_pujas` — that table does not exist.

---

## 8. Admin auth — `user_roles` check

**Added to:** `ARCHITECTURE.md`, `API_CONTRACTS.md`

`app_context=admin` on JWT is necessary but not sufficient. Admin dependency
must verify `user_roles` contains `admin` or `support`.

---

## 9. PgBouncer + psycopg3 prepared statements

**Added to:** `ARCHITECTURE.md` connection policy

Behind PgBouncer transaction mode, set `prepare_threshold=None` (disable prepared
statements) on async and sync psycopg3 connections.

---

## 10. Stuck-state monitoring

**Added to:** `ARCHITECTURE.md` monitoring section

Alert in addition to existing (`failed_permanent`, dispatch exhaustion, webhook sig):

| Condition | Alert |
|---|---|
| `payment_pending` past hold TTL + 30 min grace, payment exists | Webhook loss |
| `confirmed` past scheduled_time + 90 min, not `in_progress` | No-show / stuck |
| `refunds` `pending` with `attempt_count >= 6` | Refund stall |

---

## 11. Product policy — `advance_balance`

**Added to:** `ARCHITECTURE.md` (not a code change)

Documented in `plans/MASTER.md`:

- Default UI to `full_online`
- Commission base = `amount_due_online` only (intentional per DATABASE.md)
- Disintermediation risk acknowledged for high-relationship repeat bookings

---

## Migration 005 scope (when implementing §2 and §6)

See `spec/db/migration_005.sql`:

- `trg_refunds_cap_total` trigger
- `trg_addresses_geom_sync` trigger (BEFORE INSERT OR UPDATE on addresses)

Apply via Alembic `op.execute(open("spec/db/migration_005.sql").read())` after 004.

---

## 12. Duration guard (`P-DUR-GUARD`)

**Added to:** `DATABASE.md` migration 006; `spec/db/migration_006.sql`; `spec/db/triggers.sql`

**Problem:** Trigger 5 uses `COALESCE(duration_minutes, 60)`. If `pujas.duration_minutes = 0`,
`COALESCE(0, 60)` stays **0** → empty `tsrange` → both exclusion constraints never fire.

**Fix:**

- Trigger 5: `COALESCE(NULLIF(duration_minutes, 0), 60)` on snapshot from `pujas`.
- `CHECK (duration_minutes > 0)` on `bookings` and `pujas` (migration 006: `NOT VALID` →
  backfill → `VALIDATE CONSTRAINT`).
- Backfill before validate:
  `UPDATE bookings SET duration_minutes = COALESCE(NULLIF((SELECT duration_minutes FROM pujas WHERE id=puja_id),0),60) WHERE duration_minutes IS NULL OR duration_minutes = 0`

---

## 13. dispatch-choice guarded conversion (`P-DIRECT-CLEAR-INTENDED`)

**Added to:** `DISPATCH_FLOW.md`, `API_CONTRACTS.md`

**Problem:** `dispatch-choice` with `action=broadcast` must clear `intended_pujari_id` and
flip `dispatch_mode` to `broadcast`. Without clearing, the declined direct pujari is benched
from re-offer and overlap filters.

**Guarded UPDATE** (0 rows → 409 — not only `status_id`; see §15):

```sql
UPDATE bookings
SET intended_pujari_id = NULL, dispatch_mode = 'broadcast', updated_at = now()
WHERE id = :bid
  AND status_id = :requested_id
  AND dispatch_mode = 'direct'
  AND pujari_id IS NULL;
```

Then enqueue `broadcast_booking(booking_id)` after commit.

---

## 14. Dispatch state reset on fresh re-dispatch (`P-DISPATCH-STATE-RESET`)

**Added to:** `DISPATCH_FLOW.md`

**Problem:** `confirmed → requested` (pujari-cancel) leaves `booking_dispatch_state.round`
at its prior value. Next `rebroadcast_booking` increments from round 3 → 4 → exhaustion.

**Fix:** Reset logic lives in `_dispatch_round` when the task is enqueued with `fresh=True`
(pujari-cancel, admin return-to-requested). Normal reject/sweep rebroadcast uses
`fresh=False` (default) so rounds 1→2→3→4 are unaffected.

**Critical ordering (under the dispatch lock):** acquire `dispatch_lock:{booking_id}` NX
first, then if `fresh=True` reset state, then round CAS, then dispatch. The reset MUST
NOT run before the lock — concurrent `fresh=True` + stale sweep rebroadcast could both
reset and double-dispatch round 1. Sequence: lock → reset (if fresh) → CAS → offers.

```sql
-- inside worker: after dispatch_lock acquired, when fresh=True, before round CAS:
UPDATE booking_dispatch_state
SET round = 0, radius_km = 3.0, exhausted_at = NULL, last_dispatched = NULL
WHERE booking_id = :bid;
```

Pujari-cancel step 4: `rebroadcast_booking.delay(booking_id, fresh=True)`.

---

## 15. Mandatory guarded transitions (`P-TXN-LOCK`)

**Added to:** `DISPATCH_FLOW.md`, `project.mdc`

Every booking state write (status flip **or** mode/assignment predicate change) MUST:

1. `SELECT … FOR UPDATE` the booking row in the same transaction.
2. `UPDATE … WHERE <expected predicates>` — 0 rows → 409 `StaleBookingState`
   ("Booking state changed — refresh and retry."). Application-level, not a DB
   constraint — use one shared exception/helper (see `API_CONTRACTS.md`).

`status_id` alone is not always the guard column (see §13 dispatch-choice). Launch-gate
tests must cover concurrent transitions (customer-cancel vs pujari-start, dispatch-choice
double-tap / late-accept race).

---

## 16. GST / withholding / tax config (v1.2 — `GST_Withholding_Tax_Model_v1.2.pdf`)

**Added to:** `ARCHITECTURE.md`, `API_CONTRACTS.md`, `DATABASE.md`, `plans/MASTER.md`,
`plans/STATUS.md`, `plans/ADMIN.md` (`A-TAX-CONFIG`), `plans/CUSTOMER.md`, `plans/PLATFORM.md`,
`IDEMPOTENT_BOOKING.md`

**Companion:** [`spec/plans/A-TAX-CONFIG.md`](./A-TAX-CONFIG.md) (admin API + migration 007 ordering)

**Status:** ACCEPTED for implementation plumbing; **statutory values gated on CA memo**
(`tax_statutory_config.advisor_signoff_ref NOT NULL`).

### Policy (adopt verbatim)

> **If an ops person can change it without a CA memo, it must be a *price* — never a statutory *rate*.**

### Three-supply model (layman)

| Supply | Who → Who | GST at launch (assumed) |
|---|---|---|
| 1. Puja (ceremony) | Pujari → Customer | Likely **exempt** (Entry 13(a)) — Q1 for CA |
| 2. Samagri/materials | — | **Exclude at launch** — bundling destroys s.23(1)(a) protection |
| 3. Platform fee (e.g. ₹21) | Platform → Customer | **18%** on fee only — your certain liability |
| 4. Commission from pujari | Platform → Pujari | **0%** years 1–2 (`commission_pct` in config) |

**₹21 inclusive** → revenue ~₹17.80, GST ~₹3.20 (CGST/SGST or IGST per address). **Not** GST on full puja price.

### Split config tables (grant-enforced — not one table + labels)

| Table | Class | Written by |
|---|---|---|
| `tax_commercial_config` | Prices: `platform_fee_gross`, `platform_fee_inclusive`, `commission_pct` | Admin API (`puja_app` INSERT only) |
| `tax_statutory_config` | Rates + legal enums: GST%, TDS%, thresholds, `puja_gst_treatment`, etc. | **`puja_migrate` only** — `REVOKE INSERT` from `puja_app` |

Temporal model: **latest-wins** `effective_from DATE UNIQUE` — append-only, no UPDATE to close rows.
Current = `ORDER BY effective_from DESC LIMIT 1 WHERE effective_from <= CURRENT_DATE`.

### Snapshot timing (critical)

- **`tax_*_config_id` + `platform_fee_gross` + `total_charged_online` snapshotted on `slot_holds`** at quote/hold.
- **`POST /v1/bookings` inherits from hold** — never re-reads current config.
- **Razorpay order amount = `total_charged_online`** (= `amount_due_online` + `platform_fee_gross`), not `amount_due_online` alone.

### Income-tax TDS (s.393, ex-194-O) — P0, not gated on GST memo

- 0.1% on gross facilitated when pujari FY > ₹5L and operative PAN; 5% if no/inoperative PAN.
- Applies to **full puja value** including `advance_balance` offline portion (Example B).
- **s.197 / Form 13** — lawful nil deduction for top pujaris (`P-197-ASSIST`, Phase 5); PAN prerequisite now (`B-KYC` DigiLocker pull).

### IGST at launch (not deferred)

- Out-of-state customer booking in-city puja → likely **IGST** on ₹21 fee (Rule 46 / POS — Q17).
- Requires `users.billing_state_code` — **re-opens `C-ADDR`** (service address ≠ billing state).

### RBI / Razorpay Route (§15 — urgent, non-tax)

Confirm **Razorpay Route** split settlement before taking money. Pujari funds must not rest in platform operating account (`P-RAZORPAY-ROUTE`).

### Phase 3 task gates

| Task | Gate |
|---|---|
| `P-GST-MODEL` | BLOCKED — CA signed memo → `advisor_signoff_ref` |
| `P-SPLIT-CONFIG`, `P-SPLITS`, migration 007 schema | **PENDING** — plumbing unblocked; values from memo |
| `A-TAX-CONFIG` | Commercial fields only; blocked_by: `P-ADMIN-ROLE`, migration 007 |
| `P-TDS-393` | P0 — not gated on GST memo |
| `P-IGST` | blocked_by: `billing_state_code` |
| `P-INVOICE-SERIES` | blocked_by: Q16 (consolidated vs per-booking) |

### Advisor brief

Send PDF §11 (**17 questions**) verbatim; store memo ref in `tax_statutory_config.advisor_signoff_ref`.
**Q15 (aggregate turnover / principal vs agent)** is highest leverage.

### Correctness fix

ARCHITECTURE.md must **not** model GST as `% of commission` when `commission_pct = 0` — GST is on **platform fee** per supply #3.

**Rule:** `P-SPLITS` and `P-PAYOUT` read **snapshotted** `tax_statutory_config_id` + `tax_commercial_config_id` on each booking — never recompute from "current" config on refund.

---

## 17. Multi-provider SMS failover (FAST2SMS + MSG91)

**Added to:** `ARCHITECTURE.md`, `API_CONTRACTS.md`, `DISPATCH_FLOW.md`, `PLATFORM.md`

### Router

- **`app/services/sms_router.py`** — single entry for all OTP + transactional SMS.
- **`SMS_PROVIDER_ORDER`** env — comma-separated chain, e.g. `fast2sms,msg91`.
  Tries left→right; logs `sms_provider` on success; all-fail → `sms_sent=false`
  (dev: `DEBUG=true` logs `otp_dev_only`).

### Providers

| Provider | Config | Launch default |
|---|---|---|
| **FAST2SMS** | `FAST2SMS_API_KEY`, `FAST2SMS_OTP_ROUTE=otp`, `FAST2SMS_QUICK_ROUTE=q` | **Primary** — Dev API, no DLT header on Quick SMS |
| **MSG91** | `MSG91_AUTH_KEY`, `MSG91_TEMPLATE_ID`, `MSG91_ENABLED` | **Held** — `MSG91_ENABLED=false` until DLT + SendOTP template |

### MSG91 Widget vs server API (critical)

The MSG91 dashboard **OTP Widget** (`widgetId`, `tokenAuth`) is a **client-side embed**
for Flutter/Web — **not** used by this backend. Server integration uses:

- MSG91 **SendOTP REST API** (`MSG91_AUTH_KEY` + template id from **OTP → Templates** with `##OTP##`)
- FAST2SMS **Dev API** (`bulkV2`)

### DLT required for test sends (India)

FAST2SMS and MSG91 both operate under TRAI DLT rules. **Registration is mandatory before
any SMS can be delivered — including test/sandbox traffic.** Symptoms when DLT is missing:

- API may return success or a generic error, but **no SMS arrives**
- Provider dashboard shows template/header/entity validation failures

**Do not** interpret this as the backend failing to reach the vendor. Requests typically
reach the provider; delivery is blocked at compliance. Until DLT is approved:

- Run auth flows with `DEBUG=true` — OTP logged as `otp_dev_only` when `sms_sent=false`
- Prove router integration with `tests/test_sms_router.py` (mocked HTTP)

### When DLT is ready

```bash
MSG91_ENABLED=true
SMS_PROVIDER_ORDER=msg91,fast2sms   # optional: flip primary
```

No code change — env only.

### Files

| File | Role |
|---|---|
| `app/services/sms_router.py` | Failover orchestrator |
| `app/services/fast2sms_client.py` | FAST2SMS HTTP |
| `app/services/msg91_client.py` | MSG91 SendOTP + Flow |
| `app/services/sms_phone.py` | India phone normalization |
| `app/workers/notifications.py` | FCM + `sms_router` transactional fallback |

---

## 18. Phase 2 live verification gates (DLT + Flutter)

**Added to:** `ARCHITECTURE.md`, `MASTER.md`, `STATUS.md`, `PLATFORM.md`, `project.mdc`

Phase 2 **backend code** (`P-SMS-ROUTER`, `P-AUTH`, `P-NOTIFY`, `B-DEVICE`) is complete
when unit/integration tests pass. **Live vendor verification** has two external gates:

### P-SMS-DLT — Live SMS delivery

| Item | Policy |
|---|---|
| Blocker | TRAI DLT: registered principal entity, sender ID (header), approved template with `##OTP##` or transactional text |
| Applies to | FAST2SMS and MSG91 — **including test sends** |
| Not a backend bug | HTTP may reach vendor; message rejected or dropped without DLT |
| Until unblocked | `DEBUG=true` → `otp_dev_only` in logs; E2E UI can still test auth with logged OTP |
| Unblock criteria | DLT approved on provider dashboard; one real OTP received on a test handset |

### P-FCM-E2E — Live push notifications

| Item | Policy |
|---|---|
| Blocker | Flutter app (customer + pujari flavors) with `firebase_messaging` |
| Backend ready | `fcm_client.py`, `notifications` worker, `POST /v1/me/devices` |
| Until unblocked | Mock FCM in `test_phase2_notifications.py`; pujari poll `GET /v1/offers` every 3–5s |
| Unblock criteria | Flutter registers token → dispatch triggers FCM → notification received on device |

### Phase 2 phase-complete rule

Phase 2 → **COMPLETED** when: `P-WS` location events done, **and** at least one successful
live SMS (post-DLT) **and** one successful live FCM (post-Flutter) on a test device.

---

## 19. Phase 4 admin control plane (catalogue, ops, RBAC)

**Added to:** `ADMIN.md`, `MASTER.md`, `STATUS.md`, `API_CONTRACTS.md`, `DISPATCH_FLOW.md`,
`A-TAX-CONFIG.md`, `project.mdc`

### Milestones (do not conflate)

| Milestone | Meaning |
|---|---|
| **Phase 4 complete** | Ops run marketplace from admin UI without SQL — catalogue, KYC, search, reassign, audit |
| **Go-live** | Phase 3 unblocked — CA memo, Razorpay Route, splits, payouts, checkout tax snapshot |

Phase 4 may proceed **while Phase 3 is ON HOLD**.

### Sprint 4-0 — P0 security hotfixes (five tasks + migration 009 — `auth.py` + `security.py`)

**Migration 009 ships in Sprint 4-0, not 4A** — `P-AUTH-FIX` needs `refresh_jti`,
`P-ADMIN-SEED` needs the `roles` seed, `P-ADMIN-AUTH` needs `admin_credentials`. The
audit table / `revoked` status / promo CHECK in 009 are inert until 4A/4C code uses them.
Build order: `P-ADMIN-AUTH-FIX` → mig 009 → `P-AUTH-FIX` → `P-ADMIN-SEED` → `P-ADMIN-ROLE`
→ `P-ADMIN-AUTH` (SEED before ROLE — role rows must exist before anything checks them).

**First-admin TOTP enrolment:** the bootstrap seeds a role but no credential, and
enrolment normally requires being logged in (`users.email` is nullable, so magic-link
can't rescue the bootstrapped admin either). Rule: a role-holder with **no**
`admin_credentials` row may **self-enrol TOTP exactly once** on first admin login;
re-enrolment after activation requires an existing admin reset. Covers all future
admins, not just the first.

**`P-ADMIN-AUTH-FIX`** — close query-param escalation (verified in code):

- `otp_verify(..., app_context: str = "customer")` is a FastAPI **query parameter**.
  Any phone passing OTP can request `?app_context=admin`; no role check; user auto-created.
- Fix: `app_context` on **`OtpVerify` body** (`customer` | `pujari` only for SMS). Admin never
  via SMS (`P-ADMIN-AUTH`).

**`P-AUTH-FIX`** — refresh/logout + OTP lockout (verified in code):

- `refresh` / `logout` use `refresh_token_hash == hash_secret(token)`. `hash_secret` uses
  bcrypt + `gensalt()` → lookup always fails. Fix: store JWT `jti` on `auth_sessions`, lookup
  by `jti`, `verify_secret` against stored hash.
- Failed OTP: `attempts += 1` then raise inside `get_db_txn` → rollback → counter never
  persists. Fix: Redis counter or autonomous write outside verify transaction.

**`P-ADMIN-ROLE`** ships **before** Sprint 4A:

1. OTP verify: refuse `app_context=admin` without `user_roles` (`admin` | `support`)
2. `require_admin`: load roles from DB; populate `Principal.roles`

`A-ADVANCE` is already live — this closes a production auth gap.

**`P-ADMIN-SEED`** — roles are never seeded:

- `seed.sql` seeds only `status_types`; the `roles` table is **empty** — `P-ADMIN-ROLE`
  would check `user_roles` against names that don't exist. Migration 009 seeds
  `('admin')`, `('support')`.
- First-admin bootstrap: role assignment is admin-only → chicken-and-egg. One-time
  script or env-keyed migration INSERT; then `POST /v1/admin/users/{id}/roles`.

**`P-ADMIN-AUTH`** — admin login must not depend on SMS OTP:

- The only auth path today is SMS OTP; `P-SMS-DLT` is BLOCKED → no DLT = no production
  admin login. Phase 4's exit gate would silently depend on a compliance task.
- Fix: TOTP (authenticator app) or email magic-link for `app_context=admin`, restricted
  to `user_roles` admin/support. Standard back-office practice; removes DLT from Phase 4.
- **TOTP secret storage:** TOTP secrets **cannot be hashed** — verification needs the
  plaintext. Store them app-layer **encrypted** (AES-GCM/Fernet, dedicated `TOTP_ENC_KEY`
  from the secrets manager — never `SECRET_KEY`, never plaintext). ARCHITECTURE.md's
  hash-only rule applies to OTPs/refresh tokens, not TOTP seeds. Decide key sourcing
  (env vs SSM) before writing migration 009's `admin_credentials` table. Magic-link
  tokens are single-use + short-lived → those ARE hashed like OTPs.
- Per-context token TTL: admin refresh ≤ **1 day** (an account that can override refunds
  and edit the catalogue must not carry a 30-day refresh token).

### New admin tasks (track: `ADMIN.md`)

| ID | Scope |
|---|---|
| `A-CAT-CATEGORIES`, `A-CAT-PUJAS`, `A-CAT-ADDONS` | Catalogue CRUD (soft-disable only) |
| `A-PUJARI-PRICING` | `pujari_pricing` matrix |
| `A-PUJARI-SEARCH`, `A-BOOKING-DETAIL` | Ops directory + 360° booking |
| `A-AUDIT-LOG` | Append-only audit; log PII reads (DPDP) |
| `A-MONEY-READ` | Read-only money; label "settlement pending" until `P-SPLITS` |
| `A-ADMIN-UI` | Next.js admin shell |

### A-REASSIGN implementation traps (normative)

Manual reassign must, in one transaction:

- **Revoke the old accepted row** → `('assignment','revoked')` (migration 009 seed).
  Otherwise the booking keeps two `accepted` assignments forever — the live-offer
  index can't catch resolved rows. Never reuse `rejected` (poisons reliability scoring).
  Trigger-3-safe: non-accepted status skips the trigger body.
- INSERT with `expires_at = now() + interval '5 minutes'` (Guard 1 rejects `<= now()` on INSERT)
- INSERT with `responded_at = now()` (clears `ux_booking_assignments_one_live`)

Block reassign on `in_progress` / terminal — use `A-DISPUTE`.
`LG-manual-reassign` asserts exactly one `accepted` assignment after reassign.

### A-KYC approval model (physical-safety gate)

Approving one document must **not** flip the whole pujari to `verified`
(`doc_type` is free-text; a selfie alone would verify someone entering customers' homes):

- Required `doc_type` set defined in app config
- Approve/reject acts on the **document**; `pujaris.verification_status='verified'` is
  promoted only when **every required** doc_type has `is_current=true, status='verified'`
- Pending queue filters `is_current = true`
- Approve/reject = `admin` role only; `support` views and recommends

### A-AREAS deactivation guard

No booking→area link exists (and `service_areas.pincode` is nullable). Guard path:
`service_areas → pujari_service_areas → pujaris → active bookings`. Block deactivation
when count > 0, or require explicit confirm showing the count.

### A-PROMO validation

`promo_codes` lacks `valid_until > valid_from` CHECK — migration 009 adds the CHECK
(`ads` pattern) **and** the handler validates for a clean 422. Both, not either.

### Audit log integrity

`puja_app`'s default grant is SELECT/INSERT/**UPDATE** (ARCHITECTURE.md §Database roles) —
"no DELETE" alone is not append-only. Migration 009 must
`REVOKE UPDATE, DELETE ON admin_audit_log FROM puja_app`.
**Dev guard:** local `.env` often connects as `postgres`; `puja_app` role may not exist
(`CURSOR_SETUP.md` creates it manually). Migration 009 must **skip REVOKE when the role is
absent** (`DO $$ … IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'puja_app') …`) so
migrations do not abort on developer machines.
**Ordering trap (the guard alone is not enough):** migrations run once per database. If prod
creates `puja_app` *after* 009 ran, the guarded REVOKE was silently skipped forever and the
"append-only" table is UPDATE-able by the app — with the migration marked applied, so nothing
alarms. Two-part fix: (1) `puja_app` role creation is a documented **prerequisite of 009** in
the prod runbook; (2) all role grants/revokes also live in an **idempotent
`scripts/apply_grants.sql`** executed on every deploy. The migration guard exists only so dev
machines don't abort — prod correctness relies on the deploy script, never the guard.
**Also audit `booking_status_history`** — it is "the audit trail for disputes" yet
UPDATE-able by the app role today; add the same REVOKE in migration 009.
Failed admin actions are logged via structlog out-of-transaction (in-transaction audit
rows roll back with the failed mutation).

### RBAC

| Role | Notes |
|---|---|
| `admin` | Full access; uncapped refund override |
| `support` | Ops + KYC; **capped** refund override; no catalogue/tax write |

### Migration numbering (canonical)

| Migration | Scope |
|---|---|
| **007** | Tax tables + booking/hold snapshot columns |
| **008** | `P-PLL-GEOM` optional trigger |
| **009** | `admin_audit_log` + guarded `REVOKE UPDATE, DELETE FROM puja_app` (also on `booking_status_history`) · seed `('assignment','revoked')` · seed `roles` · `auth_sessions.refresh_jti` · `promo_codes` date CHECK · TOTP storage |

Fixes `PLATFORM.md` / `DISPATCH_FLOW.md` / review log references that incorrectly used 007 for PLL-GEOM.

### Phase 3 ON HOLD

No checkout tax snapshot, `P-SPLITS`, or `P-PAYOUT` until CA memo + Razorpay Route.
Phase 4 tax UI: **GET only** after migration 007 DDL; commercial **POST** after statutory seed.

---

## 20. Phase 4B catalogue Wave-0 (content model + price resolver)

**Added to:** `ADMIN.md`, `MASTER.md`, `DATABASE.md`, `API_CONTRACTS.md`, `STATUS.md`

**Gate:** Write §20 and apply migration **011** (content model) **before** shipping admin
catalogue CRUD/UI beyond baseline categories. Implement **`pricing_resolver`** (§20.3)
**before** `A-PUJARI-PRICING` admin UI — otherwise ops can create listing vs checkout
price mismatches at scale.

### §20.1 — Catalogue content model

Extensions to existing tables (migration **011**):

| Table | Additions |
|---|---|
| `puja_categories` | `slug` (unique, immutable), `description`, `display_order`, `is_active`, `image_media_id` |
| `pujas` | `slug`, `tagline`, `display_order`, `price_max`, `hero_media_id`, `created_at`, `updated_at` |
| `puja_addons` | `description`, `display_order` |

New tables:

- **`puja_content_items`** — normalized bullets per puja: `kind` ∈
  `inclusion|exclusion|insight|requirement|faq_q|faq_a`, `position`, `text`, `is_active`
- **`puja_media`** — catalogue CDN objects: `entity_type`, `entity_id`, `s3_key`, `alt_text`,
  `position`, `upload_status` ∈ `pending|ready|failed`, `is_active`, `confirmed_at`

Constraints:

- `CHECK (price_max IS NULL OR price_max >= default_price)` on `pujas`
- **Slug rule:** set once at create; **immutable** after create (no auto-regenerate on rename)
- **Ordering:** customer + admin lists use `ORDER BY display_order, id`

### §20.2 — Media pipeline (catalogue)

- **Bucket:** public-read catalogue bucket only — `S3_BUCKET_CATALOG` (not `S3_BUCKET_KYC`)
- **Key:** `catalog/{entity_type}/{uuid}.{ext}`
- **Public URL:** `S3_CATALOG_PUBLIC_URL` (CDN base — never raw S3 endpoint in customer APIs)
- **Lifecycle:** `upload_status='pending'` → client PUT → `POST .../confirm` (S3 HEAD) →
  `ready`. Customer APIs return only `upload_status='ready'` rows.
- **Presign policy:** enforce `content-length-range` + allowlisted `Content-Type`
- **Orphan reclaim:** stale `pending` >24h — sweep spec'd; implementation 4C tail

### §20.3 — Price resolver contract (P0)

**Problem (verified in code before Wave-0):** `GET /v1/pujaris` priced from
`pujari_pricing.base_price` while `checkout/quote` and `POST /bookings` used
`pujas.default_price` only — direct-booking customers could see one price and pay another.

**Single implementation:** `app/services/pricing_resolver.py`

```text
resolve_puja_unit_price(db, puja_id, pujari_id=None) -> Decimal

  direct (pujari_id present):
    COALESCE(pujari_pricing.base_price, pujas.default_price)

  broadcast (pujari_id absent):
    pujas.default_price

resolve_catalog_display_range(db, puja_id) -> (price_from, price_to):
    price_from = MIN(verified pujari_pricing.base_price) OR default_price
    price_to   = pujas.price_max OR price_from
```

**Consumers (no duplicate price logic in endpoints):** `checkout_quote`, `compute_amounts`,
future `GET /v1/pujas` range display, `GET /v1/pujaris` (must match resolver for same pair).

**API:** `GET /v1/checkout/quote` accepts optional `pujari_id` — pass hold's pujari for
direct-mode checkout so quote matches charge.

### §20.4 — Hold / booking snapshot boundary

| Artifact | Price behaviour |
|---|---|
| **Existing bookings** | `bookings.total_amount` + `booking_addons.price_at_booking` snapshotted at insert — admin catalogue edits do not rewrite |
| **Active holds + quote window** | **Not snapshotted today** — quote and booking read **live** resolver at request time. Admin price change can re-price between quote and `POST /bookings` |
| **Phase 3 `C-HOLD`** | Will snapshot unit price (+ tax fields) on `slot_holds` at hold creation; bookings inherit — never re-read current |

Until `C-HOLD` ships: admin **impact** endpoints + UI must warn on price/duration changes when
active unreleased holds exist.

### §20.5 — Addon media + seed idempotency (migration **021**)

**Added:** Hyderabad launch catalogue MVP — addon images, bootstrap seed safety.

| Change | Detail |
|---|---|
| `puja_addons.image_media_id` | Optional FK → `puja_media(id)` `ON DELETE SET NULL` |
| `puja_media.entity_type` | CHECK extended with `'addon'`; S3 key `catalog/addon/{uuid}.ext` |
| Customer API | `CustomerAddon.image_url` via `media_urls_by_ids()` — `upload_status='ready'` AND `is_active=true` only |
| `UNIQUE (puja_id, name)` on `puja_addons` | Idempotent seed upsert; preserves `id` for `booking_addons` FK — **never DELETE addons in seed** |
| `UNIQUE (puja_id, kind, position)` on `puja_content_items` | Content seed upsert safety |
| Apply path | `spec/db/migration_021.sql` + `scripts/apply_migration_021.py` (not Alembic `021`) |

**Ops:** soft-disabled addon blocks re-create with same name (`UNIQUE`). Addon `display_order` set at create only (reorder API deferred).

### Migration numbering (Wave-0)

| Migration | Scope |
|---|---|
| **010** | Early slice: `puja_categories.is_active` (may already be applied on dev DBs) |
| **011** | Wave-0 full content model: §20.1 tables/columns, slug/order backfill, `price_max` CHECK |
| **012** | Puja MVP launch policy (§21): `addresses.service_area_id`, `booking_dispatch_state.dispatch_starts_at` / `dispatch_deadline`, `relationship_managers`, `pujas.is_muhurat_bound`, `platform_settings` dispatch keys |

---

## 21. Puja MVP launch policy (geo, dispatch, contact) — July 2026

**Added to:** `LAUNCH_POLICY.md`, `DISPATCH_FLOW.md` §Puja MVP launch dispatch,
`API_CONTRACTS.md` §Launch policy, `ARCHITECTURE.md`, `DATABASE.md` migration **012**,
`MASTER.md` product policy, `PARTNER.md`, `CUSTOMER.md`, `PLATFORM.md`, `STATUS.md`,
`.cursor/rules/project.mdc`.

**Product intent:** Scheduled religious-service marketplace — **not** a taxi/ride-hail
clone. Launch optimises for broadcast supply, RM-mediated coordination, and DB integrity.

### §21.1 — Dispatch mode (broadcast only at launch)

- All new bookings are created with `dispatch_mode = 'broadcast'` and
  `intended_pujari_id = NULL` at checkout.
- **Direct booking is disabled** at API/UI: no `pujari_id` on `slot-holds`, no
  `dispatch-choice` endpoint exposure, no `direct_dispatch` worker enqueue.
- **Schema retained (do not drop):** `bookings.dispatch_mode`, `bookings.intended_pujari_id`,
  trigger 3 write of `intended_pujari_id` on **every** accept, and
  `ex_bookings_intended_no_overlap`. These protect broadcast accepts and paid-slot
  integrity — removing them opens double-payment holes (see DISPATCH_FLOW.md race matrix).
- Phase 2 may re-enable direct booking when ratings/supply support “book this pujari”.

### §21.2 — Geo / presence (no pujari GPS at launch)

- `PUT /v1/me/heartbeat` sets Redis `presence:{pujari_id}` TTL only; `{lat,lng}` is
  **optional** at launch. `DELETE /v1/me/heartbeat` = go offline (unchanged).
- Dispatch eligibility **must not** require `pujari_live_location.geom` or `ST_DWithin`
  at launch. Fallback: verified + priced + online (Redis) + active city service area
  membership (`pujari_service_areas` join) + availability/unavailability + overlap filters.
- Customer `addresses.geom` remains **required** at checkout (job-site pin — not live tracking).
- Phase 2: optional `{lat,lng}` on heartbeat; re-enable radius dispatch per
  `booking_dispatch_state.radius_km` schedule (3/6/10/15 km).

### §21.3 — Service area label (display only)

- Customer address create/update requires `service_area_id` referencing an **active**
  `service_areas` row (admin-managed list: Kukatpally, LB Nagar, KPHB, Miyapur, …).
- **Display only at launch:** area label appears on pujari offer cards; dispatch still
  broadcasts to **all eligible city pujaris** (not filtered by customer's area).
- Phase 2: optional dispatch filter by area when per-zone supply exists.
- No polygon geofencing; no Google reverse-geocode as source of truth — dropdown only.

### §21.4 — Information revealed (privacy)

| Stage | Customer sees | Pujari sees |
|-------|---------------|-------------|
| **Offer (before accept)** | Own full address (they entered it) | Puja, date/time, money, **area label only** — no street/house, no customer phone |
| **After confirm** | Assigned **pujari name** + **RM** (name, phone) | **Full service address** + static map link (`https://maps.google.com/?q=lat,lng`) + **RM** — **no customer phone** |

- **RM (relationship manager):** platform mediator who conferences customer ↔ pujari.
  Launch: one or few rows in `relationship_managers`; assign per booking or default
  active RM for city. Phase 2: call masking (Exotel/Knowlarity) may replace RM for
  routine coordination — design fields generically.

### §21.5 — Overlap and travel buffer

- **Hard (DB):** `ex_bookings_pujari_no_overlap` on actual service window
  `[scheduled_time, scheduled_time + duration_minutes)` — unchanged.
- **Soft (app):** configurable `dispatch_buffer_minutes` (default **60**) in
  `platform_settings`. Enforced in **dispatch eligibility** and **accept-time check** —
  **not** widened into the exclusion constraint (allows same-building back-to-back
  override by ops later).
- Accept-time: if within buffer of another confirmed booking, return **409** with
  travel-buffer copy (distinct from overlap copy).

### §21.6 — Deferred dispatch windows (replaces radius rounds at launch)

> **Superseded by §21.6.A–H (Dispatch v2, July 2026).** Under Dispatch v2 the first
> broadcast fires **immediately on payment** for every booking (`immediate_dispatch_on_payment=true`),
> classification is a **frozen `booking_class` enum** (not a live lead-hours recompute), and
> partner UX splits into instant modal vs advance inbox. The deferred `advance_dispatch_start_hours`
> model below is **retained only for rollback** (flip the flag false). Read §21.6.A–H before any
> dispatch, booking-gate, offer-TTL, or reconfirmation change.

Settings in `platform_settings` (defaults shown):

| Setting | Default | Meaning |
|---------|---------|---------|
| `instant_lead_hours` | `4` | Bookings with slot ≤ this many hours away = **instant** |
| `instant_dispatch_minutes` | `30` | Instant: offer window from first broadcast until fail |
| `advance_dispatch_start_hours` | `4` | Advance: first broadcast at `slot − N hours` |
| `advance_dispatch_fail_hours` | `3` | Advance: `failed_no_pujari` + refund at `slot − N hours` if unaccepted |
| `reoffer_cooldown_minutes` | `45` | Re-ping **expired** ignorers after cooldown |
| `dispatch_buffer_minutes` | `60` | Soft travel buffer (§21.5) |

**`booking_dispatch_state` (migration 012):** add `dispatch_starts_at`, `dispatch_deadline`.
Sweep/worker broadcasts only when `now() >= dispatch_starts_at AND now() < dispatch_deadline`.

**Re-offer policy (status-aware):** never re-offer pujaris with a **rejected** assignment
for this booking. **Expired** ignorers may be re-offered after `reoffer_cooldown_minutes`.
Newly-online pujaris who were never offered are always eligible.

**Legacy columns** `round`, `radius_km`, `max_rounds` remain for Phase 2 geo dispatch;
launch exhaustion is **time-based** (`dispatch_deadline`), not round-count.

### §21.6 Dispatch v2 — immediate dispatch, dual partner UX (A–H)

**Approved July 2026 (architect review v4.1).** DDL: migration **014** (chains after 013).
Supersedes the deferred model in §21.6 for launch. Task: `P-LAUNCH-DISPATCH-V2` in `plans/STATUS.md`.

**Two fields, two lifetimes — do not conflate:**

| Concept | Field | When set | Used for |
|---|---|---|---|
| **Policy classification** | `bookings.booking_class` ∈ `{instant, advance}` | **Once**, at `POST /v1/bookings` insert | Night gate, offer-TTL choice, RM rules, failure cutoff, reconfirmation |
| **Partner UX urgency** | `urgency` (computed, never stored) | **Read time**, `GET /v1/offers` | Modal vs inbox, post-flip FCM |

`booking_class` is a **frozen enum**, not a live `lead_hours` recompute: a later change to
`instant_lead_hours` MUST NOT reclassify an in-flight booking. The night gate and RM/failure
logic key off the frozen class; only the modal-vs-inbox choice keys off live `urgency`.

#### §21.6.A — Frozen `booking_class` + single authoritative gate

Classification (once, at insert; Asia/Kolkata):

```
lead_hours    = (scheduled_date + scheduled_time - now()) in hours
booking_class = 'instant' if lead_hours <= instant_lead_hours else 'advance'
```

Single authoritative gate — `POST /v1/bookings`, **before** the Razorpay order is created:

```
is_night = (00:00 <= scheduled_time < 06:00)   # IST
Rule 1 (permanent):  booking_class == 'instant' AND is_night  -> 422 INSTANT_NIGHT_BLOCKED
Rule 2 (launch, 2a): is_night AND NOT night_bookings_enabled  -> 422 NIGHT_BOOKINGS_DISABLED
```

- `POST /v1/slot-holds` is an **advisory UX pre-check only** — it does not freeze `booking_class`
  and is not authoritative (the customer can dwell in checkout and cross a boundary; the gate at
  `POST /v1/bookings` is the one that counts).
- **No** live policy recompute at the payment webhook — the webhook and worker read the frozen class.
- **Launch decision 2a:** all night slots (00:00–05:59) are blocked (`night_bookings_enabled=false`).
  Night muhurats arrive with §22 muhurat consultation in Phase 2 (consulting-priest direct offer);
  `accepts_muhurat_night` is **not** added.

migration 014 (A):

```sql
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS booking_class VARCHAR(10);
UPDATE bookings SET booking_class = 'advance' WHERE booking_class IS NULL;
ALTER TABLE bookings
    ALTER COLUMN booking_class SET NOT NULL,
    ADD CONSTRAINT ck_bookings_class CHECK (booking_class IN ('instant','advance'));
-- fail-closed: no column default; POST /v1/bookings must set it explicitly

INSERT INTO platform_settings (key, value_json) VALUES
    ('night_bookings_enabled', 'false'::jsonb)
ON CONFLICT (key) DO NOTHING;
```

#### §21.6.B — Sibling-offer resolution on first accept

**Why required:** the 24h advance TTL (§21.6.D) + the sweep step-3 carve-out mean losing offers no
longer self-expire in ~120s. Without proactive resolution they linger in the live indexes for up to
24h per confirmed advance booking and keep appearing as tappable (409-ing) offers in losers' inboxes.

**Rule:** on the **first** accept (trigger 3 sets `bookings.pujari_id`), in the **same transaction**,
resolve every **other** live offer for that booking: `responded_at = now()`, `status_id -> superseded`.

**Owner: trigger 3** (`trg_set_booking_pujari_on_accept`), inside `IF v_current_pujari_id IS NULL THEN`,
immediately after the `booking_status_history` INSERT — **not** `offer_service.py` (an app-layer write
would race the trigger and miss concurrent inserts).

migration 014 (B):

```sql
INSERT INTO status_types (domain, code, label) VALUES
    ('assignment', 'superseded', 'Superseded')
ON CONFLICT (domain, code) DO NOTHING;

-- CREATE OR REPLACE trg_set_booking_pujari_on_accept(): after the history INSERT,
-- inside IF v_current_pujari_id IS NULL THEN:
--   UPDATE booking_assignments
--   SET status_id = (SELECT id FROM status_types WHERE domain='assignment' AND code='superseded'),
--       responded_at = now()
--   WHERE booking_id = NEW.booking_id AND id <> NEW.id AND responded_at IS NULL;
```

Complements the §21.6.D refresh guard (`b.status='requested' AND responded_at IS NULL`).

#### §21.6.C — Immediate dispatch on payment

- Setting `immediate_dispatch_on_payment=true` (014). Rollback = flip false (re-arms deferred advance
  start; instant is immediate in both modes).
- **Webhook** (`webhook_service.py`): set `paid_at`, flip to `requested`, write history, convert hold,
  **enqueue `broadcast_booking`**. It does **not** compute dispatch windows or write
  `booking_dispatch_state` — **delete** that block (see §21.6.H, ownership reconciliation).
- **Worker** owns the state row: `INSERT booking_dispatch_state … ON CONFLICT DO NOTHING`, then
  `ensure_dispatch_windows()` computes the windows once:
  - `advance` → `dispatch_starts_at = now()` (immediate; was `slot − advance_dispatch_start_hours`).
  - `dispatch_deadline` stays **class-aware** (unchanged from `compute_dispatch_windows()`):
    instant `now() + instant_dispatch_minutes`; advance `slot − advance_dispatch_fail_hours`.
    **Do not** set a uniform `slot − 3h` deadline for all classes — that fails instant bookings on creation.
- `advance_dispatch_start_hours` is retained for rollback only.

#### §21.6.D — Advance offer TTL + sweep step-3 carve-out

- Offer TTL by frozen class **at creation**: instant `now() + instant_offer_ttl_seconds` (120);
  advance `now() + advance_offer_ttl_hours` (24).
- **Carve-out:** core-sweep step 3 (expire `offered` past `expires_at` + set `responded_at`)
  **skips** advance-class live offers while `bookings.status='requested'`, `dispatch_deadline > now()`,
  and `urgency_escalated_at IS NULL`. Instant offers keep the existing step-3 behaviour (expire → rebroadcast).
- **`refresh_advance_offers`** — a **separate beat task** (not the 30s core sweep), **in-place UPDATE only**
  (never INSERT — a new row trips `ux_booking_assignments_one_live`), guarded on booking status:

```sql
UPDATE booking_assignments ba
SET    expires_at = now() + advance_offer_ttl_hours * interval '1 hour'
FROM   bookings b, booking_dispatch_state bds
WHERE  ba.booking_id = b.id AND bds.booking_id = b.id
  AND  ba.responded_at IS NULL
  AND  b.booking_class = 'advance' AND b.status = 'requested'
  AND  bds.urgency_escalated_at IS NULL
  AND  (bds.dispatch_deadline IS NULL OR bds.dispatch_deadline > now());
```

The status guard is mandatory — without it the task resurrects offers for already-confirmed/cancelled
bookings back into the live index permanently.

#### §21.6.E — Advance→instant urgency flip

- `urgency` is computed at read time (`GET /v1/offers`) from live `lead_hours` vs `instant_lead_hours`;
  `booking_class` stays frozen. An advance booking that crosses the threshold **escalates its UX**
  (inbox → modal), not its policy.
- `booking_dispatch_state.urgency_escalated_at` — idempotent one-shot: the flip runs
  `UPDATE … WHERE urgency_escalated_at IS NULL`; 0 rows → another tick already won.
- On flip: shorten the booking's live offers to the instant TTL and fire one high-priority
  `offer_instant` FCM to current holders. The booking then leaves §21.6.D's carve-out/refresh and
  follows the instant expire→rebroadcast path.
- **`escalate_urgency_on_threshold`** — separate beat task (~2 min cadence, own lock).
- Post-flip asymmetry: a pujari who receives their **first** offer for a now-instant booking *after*
  the flip gets it via **poll only** (read-time urgency → modal), not push. Flutter must render the
  modal whenever `urgency == 'instant'` OR `urgency_escalated == true` — never assume every modal is push-triggered.

#### §21.6.F — RM escalation for unaccepted advance bookings

Scope: `status='requested' AND pujari_id IS NULL AND booking_class='advance'`. Two idempotent markers on
`booking_dispatch_state`; each stage fires once:

- **Rule 1 (no-accept timeout, long-lead):** `now − paid_at ≥ rm_escalation_hours_no_accept` (24h) AND
  slot still `> rm_escalation_t24_hours` away AND `rm_escalated_no_accept_at IS NULL` → normal RM alert;
  set marker.
- **Rule 2 (approaching slot — also covers the 4h–48h mid-lead band):** slot `≤ rm_escalation_t24_hours`
  (24h) away AND `> advance_dispatch_fail_hours` (3h) away AND `rm_escalated_t24_at IS NULL` → urgent RM
  alert; set marker.
- **Automated backstop unchanged:** at `slot − advance_dispatch_fail_hours` (3h) an unaccepted booking is
  flipped to `failed_no_pujari` + full refund (existing dispatch exhaustion path). RM escalation gives a
  human runway *before* that automated failure — it does not replace it.
- **`rm_escalation_scan`** — separate beat task (~15 min cadence, own lock). Never run on the 30s sweep
  (RM alert loops).

#### §21.6.G — Inbox overload mitigation (accept-contention)

Immediate dispatch + 24h advance offers broadcast to the whole eligible pool → each pujari's inbox fills,
and many offers 409 because someone else accepted first.

- **G1 (chosen):** at broadcast-build, exclude pujaris already holding
  `≥ max_live_advance_offers_per_pujari` (default **15**) live advance offers. Instant offers are never suppressed.
  A capped-out pujari is picked up on the next round / as their inbox drains.
- G2 (wave/stagger by radius) is deferred to Phase 2 geo work.
- `is_still_available` on offer rows is a UI helper only; §21.6.B handles post-accept phantom removal.
- Whole-pool saturation with zero acceptances degrades to §21.6.F's RM backstop.
- `PARTNER.md` documents accept-contention 409s and "still available?" row state as expected launch behaviour.

#### §21.6.H — Partner FCM, quiet-hours reconfirmation, duration gate + reconciliations

**FCM payload types** (`notify_offers`):
- `offer_advance` — normal/data priority, routes to inbox.
- `offer_instant` — high priority, routes to modal. Sent for instant-class offers and on urgency flip.
- `accept_ack` — normal priority, **advance class only**, on accept: "Added to your Bookings — we'll
  confirm ~24h before." Closes the week-out silent-commitment gap.

**Quiet-hours reconfirmation** (settings `reconfirm_quiet_hours_start="22:00"`, `reconfirm_quiet_hours_end="08:00"`, IST):
- Ping: if the T−`reconfirm_ping_hours_before_slot` moment lands inside the quiet window, move it
  **earlier** to the preceding `reconfirm_quiet_hours_start` (more lead is always safe).
- Escalation: `max(ping_sent_at + reconfirm_escalation_hours, next reconfirm_quiet_hours_end)` — the
  escalation can never precede the ping and never fires at night.
- `reconfirmation.py` currently only parses integer settings (`_int_setting`); add a small `"HH:MM"`
  time parser for the two quiet-hours keys.

**Duration gate (`duration_minutes > 0`):** the `ex_bookings_pujari_no_overlap` window is void when
duration is 0, so Policy 3's "slot-blocking on accept is already guaranteed" holds *only* while duration > 0.
- **No new DDL.** `ck_pujas_duration_pos` / `ck_bookings_duration_pos` already exist and are VALIDATED in
  migration 006 (§12) — re-adding them in 014 throws `constraint already exists`. The residual
  `CHECK (>0)` NULL gap is unreachable: trigger 5 (`trg_snapshot_booking_duration`, BEFORE INSERT)
  coalesces `NULL/0 → puja → 60`.
- **CI assertion:** every active/bookable `pujas` row has `duration_minutes > 0` (catches catalog
  authoring mistakes by name).
- **CI concurrency gate:** two pujaris accept overlapping-window offers → exactly one wins, the other
  gets 409 `exclusion_violation` (proves Policy 3 empirically).

**Reconciliation — `booking_dispatch_state` ownership (worker, not webhook).** Today both write the row;
`DISPATCH_FLOW.md` step 0 says the worker owns it. **Delete** the `compute_dispatch_windows()` +
`INSERT booking_dispatch_state` block from `webhook_service.py` (~L134–153). The webhook ends at
`paid_at` + enqueue; the worker creates the row and fills windows (§21.6.C). Immediacy is preserved
(enqueue is immediate; sweep steps INNER-JOIN the state row, so a booking with no row yet is simply
untouched until the worker runs).

**Reconciliation — worker cadences.** The three new scans get their own beat tasks and locks; none is
added to the 30s core sweep:

| Task | Cadence | Redis lock |
|---|---|---|
| core `sweep_task` (existing) | 30s | `sweep_lock EX 25` — holds, abandon, **instant** offer expiry, rebroadcast, presence |
| `refresh_advance_offers` (D) | ~5 min | `refresh_lock` |
| `escalate_urgency_on_threshold` (E) | ~2 min | `urgency_lock` |
| `rm_escalation_scan` (F) | ~15 min | `rm_lock` |

#### §21.6 v2 — migration 014 manifest

- **Columns:** `bookings.booking_class` (+backfill +NOT NULL +CHECK);
  `booking_dispatch_state.urgency_escalated_at`, `.rm_escalated_no_accept_at`, `.rm_escalated_t24_at`.
- **Seed:** `status_types('assignment','superseded')`.
- **Trigger:** `CREATE OR REPLACE trg_set_booking_pujari_on_accept` (sibling resolution, §21.6.B).
- **Settings (`value_json`):** `night_bookings_enabled=false`, `immediate_dispatch_on_payment=true`,
  `advance_offer_ttl_hours=24`, `instant_offer_ttl_seconds=120`, `rm_escalation_hours_no_accept=24`,
  `rm_escalation_t24_hours=24`, `max_live_advance_offers_per_pujari=15`,
  `reconfirm_quiet_hours_start="22:00"`, `reconfirm_quiet_hours_end="08:00"`.
- **NOT in 014:** duplicate duration CHECKs (already in 006); `accepts_muhurat_night` (2a + §22 replace it);
  no new tables.

#### §21.6 v2 — product policy matrix

| `booking_class` (frozen) | Slot (IST) | `POST /bookings` | Dispatch | Partner UX |
|---|---|---|---|---|
| `instant` | 06:00–23:59 | Allowed | Immediate on payment | Modal + Offers tab |
| `instant` | 00:00–05:59 | **422** Rule 1 | — | — |
| `advance` | 06:00–23:59 | Allowed | Immediate on payment | Inbox; modal after urgency flip |
| `advance` | 00:00–05:59 | **422** Rule 2 at launch (2a) | — | Phase 2 / §22 |

### §21.7 — Mandatory reconfirmation (advance)

Supersedes §4 “optional launch” for bookings where `scheduled_time − now() ≥ 24 hours`:

- **24h before slot:** FCM/SMS to assigned pujari — confirm attendance.
- **No response within 4h:** admin/RM alert; RM contacts pujari and customer.
- **Quiet-hours day-shifting (Dispatch v2, §21.6.H):** ping and escalation are clamped out of
  `[reconfirm_quiet_hours_start, reconfirm_quiet_hours_end)` (default 22:00–08:00 IST) — no 2 AM ping
  for a 2 AM slot, and the escalation never precedes the ping.
- Phase 2: in-app confirm button + auto re-dispatch policy.

### §21.8 — Muhurat-bound pujas

- Add `pujas.is_muhurat_bound` (migration 012, default `false`).
- When `true`: product copy and ops treat `scheduled_time` as **hard start**; stricter
  reconfirmation; consider narrower start window in partner app (implementation tail).
- Launch: column + admin flag; strict ±window enforcement is Phase 2 UX.

### §21.9 — Partner app surfaces (launch)

- **Offers** tab: live broadcast inbox (time-sensitive).
- **Bookings** tab: confirmed/upcoming/past list; calendar UI Phase 2.
- Poll `GET /v1/offers` while on duty; FCM additive.

### §21.10 — Festival surge (risk)

Documented in `LAUNCH_POLICY.md`. No automated waitlist at launch.

### §21.11 — API additions (launch)

- `GET /v1/pujari/bookings` — assigned pujari's bookings (cursor).
- `GET /v1/pujari/bookings/{id}` — confirmed+ only; address + map link + RM; no customer phone.
- `GET /v1/service-areas` — active zones for customer dropdown (city filter).
- `GET /v1/offers` — add `area_label`, `puja_name`, `scheduled_date`, `scheduled_time`.
- `GET /v1/bookings/{id}` — add `relationship_manager` block after confirm.
- Admin: `GET/POST/PUT /v1/admin/relationship-managers` (launch: CRUD for RM rows).
- **Disabled at launch:** `POST /v1/bookings/{id}/dispatch-choice`; direct `slot-holds.pujari_id`.

### §21.12 — Do-not-break list (normative)

1. Never drop `intended_pujari_id`, trigger 3, or `ex_bookings_intended_no_overlap`.
2. Never set `bookings.pujari_id` in app code (trigger 3 only).
3. Ship heartbeat-without-GPS and dispatch-without-`ST_DWithin` in the **same PR**.
4. Keep `addresses.geom` required at checkout.
5. Do not use Razorpay auth/capture-on-accept for long-lead pujas — keep
   `full_online` / `advance_balance`.

---

## Review disposition log (merged reviews — July 2026)

Single audit trail for v3.2 architecture reviews. Implementation status: `plans/STATUS.md`.

### Accepted — fix before or during Phase 0

| ID | Finding | Fix |
|---|---|---|
| P-DUR-GUARD | Zero `duration_minutes` voids exclusion constraints | §12, migration 006 |
| P-DIRECT-CLEAR-INTENDED | dispatch-choice doesn't clear `intended_pujari_id` | §13 |
| P-DISPATCH-STATE-RESET | Dispatch state not reset on `confirmed→requested` | §14, worker `fresh=True` |
| P-TXN-LOCK | Transition handlers need guarded UPDATE pattern | §15 |
| P-SPLIT-CONFIG | No `commission_pct`/`gst_pct` in `platform_settings` | Phase 3 — `tax_*_config` migration 007 (A-TAX-CONFIG) |
| P-GST-MODEL | GST/TCS settlement model | §16 v1.2 ACCEPTED; values gated on CA memo |
| — | project.mdc vs pujari-cancel NULL `pujari_id` | carve-out in project.mdc |
| — | Local dev bring-up omits migrations 004–006 | DATABASE.md + conftest |
| P-PLL-GEOM | Optional `pujari_live_location.geom` trigger | P2, migration **008** (007 = tax); heartbeat is sole writer today |

### Closed — already implemented or overstated

| Finding | Disposition |
|---|---|
| `booking_dispatch_state` INSERT before CAS | **Closed** — `dispatch.py` L58–63 `ON CONFLICT DO NOTHING` |
| Refund amounts must use `amount_due_online` | **Closed** — dispatch, webhook, cancel paths already correct; migration 005 is backstop |
| `abandoned` without `cancelled_at` | **Rejected** — spec + sweep already set both |
| Silent `failed_no_pujari` from null geom at checkout | **Rejected** — booking returns 422 if `geom IS NULL` |
| Commission on offline portion as undocumented bug | **Rejected** — intentional in DATABASE.md; business policy |
| OTP attempts → CHECK violation | **Re-opened (P-AUTH-FIX)** — increment rolls back with failed verify txn; only Redis 10/hr is real |
| `pujari_pujas` table | **Rejected** — use `pujari_pricing` |
| Transition locking "all broken" | **Rejected** — cancel/lifecycle use `FOR UPDATE`; guarded UPDATE is mandatory going forward (§15) |
| advance_balance cherry-picking | **Product policy** — documented in MASTER.md, not P0 code |
| No review endpoint | **Post-MVP** — gate on `completed` when added |

### Accepted — fix in Sprint 4-0 / 4C (July 2026 code review)

| ID | Finding | Fix |
|---|---|---|
| P-ADMIN-AUTH-FIX | `?app_context=admin` on OTP verify mints admin JWT — no role check | Body field + TOTP-only admin path (`P-ADMIN-AUTH`) |
| P-AUTH-FIX | Refresh/logout broken (bcrypt equality lookup); OTP lockout dead | `jti` lookup + `verify_secret`; persist attempts outside txn |
| P-REFUND-CAP text | `PLATFORM.md` said `total_charged_online`; trigger caps `payments.amount` | Mark COMPLETED; align acceptance text (trigger already shipped) |
| B-KYC ↔ A-KYC cycle | `PARTNER.md` listed A-KYC as dependency — spec deadlock | B-KYC depends on B-REGISTER only; A-KYC is downstream reviewer |
| B-KYC-VENDOR (Aug 2026) | Manual S3-only KYC upload | Vendor-agnostic DigiLocker (Setu v1): migration **020**, self-healing poll finalize, camera selfie gating `photo`, `kyc_identity_registry` dedup/deny-list |
| P-EXC-ADMIN-PATHS | `exceptions.py` always 200 on active refund; pujari overlap copy on admin | Branch `"/admin/" in path` per API_CONTRACTS |
| puja_app REVOKE | Migration 009 `REVOKE … FROM puja_app` fails if role missing on dev | Guard with `pg_roles` check in migration 009 |

### Launch-gate tests (write alongside Phase 0 — not deferred to Phase 6)

- Pujari-cancel at round 3 → next dispatch starts at round 1 / 3 km (`fresh=True`)
- Customer-cancel vs pujari-start concurrent race
- dispatch-choice double-tap / late-accept race (409 on second writer)

---

## Migration 006 scope (when implementing §12)

See `spec/db/migration_006.sql`:

- Trigger 5 `NULLIF` fix
- Backfill `duration_minutes = 0` rows on `pujas` and `bookings`
- `ck_pujas_duration_pos` / `ck_bookings_duration_pos` (`NOT VALID` → `VALIDATE`)

Apply via Alembic `op.execute(open("spec/db/migration_006.sql").read())` after 005.

---

## Migration 013 scope (§21.7 reconfirmation — SHIPPED)

See `spec/db/migration_013.sql` (chains after 012):

- `booking_reconfirmations` table (`ping_sent_at`, `pujari_confirmed_at`, `rm_alert_sent_at`)
- `ix_booking_reconfirmations_escalation` partial index
- settings `reconfirm_lead_hours=24`, `reconfirm_ping_hours_before_slot=24`, `reconfirm_escalation_hours=4`

## Migration 014 scope (when implementing §21.6.A–H Dispatch v2)

See `spec/db/migration_014.sql` (chains after 013). Full manifest in §21.6 v2 above:

- `bookings.booking_class` (`NOT VALID` → backfill `'advance'` → `SET NOT NULL` + `ck_bookings_class`)
- `booking_dispatch_state.urgency_escalated_at`, `.rm_escalated_no_accept_at`, `.rm_escalated_t24_at`
- `status_types('assignment','superseded')` seed
- `CREATE OR REPLACE trg_set_booking_pujari_on_accept` — sibling supersede (§21.6.B)
- settings: `night_bookings_enabled`, `immediate_dispatch_on_payment`, `advance_offer_ttl_hours`,
  `instant_offer_ttl_seconds`, `rm_escalation_hours_no_accept`, `rm_escalation_t24_hours`,
  `max_live_advance_offers_per_pujari`, `reconfirm_quiet_hours_start`, `reconfirm_quiet_hours_end`
- **No** duplicate duration CHECK (already in 006); **no** `accepts_muhurat_night`; no new tables

Apply via Alembic `op.execute(open("spec/db/migration_014.sql").read())` after 013.

---

## 23. Flutter mobile backend contract (July 2026)

Closes API gaps before `C-FLUTTER-*` / `P-FLUTTER-*` implementation. Policy:
[`spec/plans/LAUNCH_POLICY.md`](LAUNCH_POLICY.md) (panchangam moved to launch).
Normative surface: [`spec/API_CONTRACTS.md`](../API_CONTRACTS.md) v3.4.

### §23.1 — Customer booking reads expose frozen class

- `GET /v1/bookings` and `GET /v1/bookings/{id}` include **`booking_class`**
  (`instant` | `advance`, frozen at insert).
- `POST /v1/bookings` **201/409** responses include **`booking_class`**.
- Flutter branches tracking UX on this field (not live `urgency`).

### §23.2 — Public app config (no hardcoded night rules)

- `GET /v1/app-config` (no auth): `{ night_bookings_enabled, instant_lead_hours, advance_booking_amount }`
  from `platform_settings`.
- At launch `night_bookings_enabled=false` → **all** slots 00:00–05:59 IST blocked at
  `POST /v1/bookings` (`NIGHT_BOOKINGS_DISABLED`), not instant-only.

### §23.3 — Slot-hold advisory fields (already in code; now in contract)

- `POST /v1/slot-holds` returns `advisory_booking_class` + `gate_warnings[]`.
- Authoritative gate remains `POST /v1/bookings`.

### §23.4 — Catalog muhurat flag

- `GET /v1/pujas` + `GET /v1/pujas/{id}` expose **`is_muhurat_bound`** (migration 012).

### §23.5 — Partner reconfirm ack

- `POST /v1/pujari/bookings/{id}/reconfirm` → `booking_reconfirmations.pujari_confirmed_at`.
- Decline → existing `POST /v1/bookings/{id}/pujari-cancel`.

### §23.6 — Server-cached panchangam

- Table `panchangam_daily` (migration **017**; home-ribbon columns in **018**).
- Celery beat fetches vendor once per city+date+locale+system; **mobile reads `GET /v1/panchangam` only**.
- Response labels **`panchang_system`** (`drik` | `vakya`).
- **Launch gate:** ops validates sample dates against printed Telugu panchangam before release.

**Calculation source (normative):**

| Rule | Requirement |
|------|-------------|
| **Approved engine** | [`@ishubhamx/panchangam-js`](https://github.com/ishubhamx/Hindu-Panchangam-Legal) (MIT) — same engine as [telugu-panchangam-app](https://github.com/suhasatluri/telugu-panchangam-app) (MIT, self-hostable). Uses `astronomy-engine` (MIT), not Swiss Ephemeris. |
| **Server only** | Vendor URL / compute keys live in backend env (`PANCHANGAM_VENDOR_URL`). Flutter never calls vendor APIs or npm packages. |
| **Self-host** | Production MUST self-host the adapter or engine — do not depend on `telugupanchangam.app` public API (rate limits, external SPOF). |
| **`drik`** | Maps to engine default (Drik Ganita). Worker populates cache at launch. |
| **`vakya`** | Reserved for traditional Vakya tables (Phase 2). Until adapter ships, worker may skip `vakya` rows; `GET` returns **404** for cache miss. |

**Home-ribbon fields (migration 018 — required in API response when cache row exists):**

| API field | Telugu label | Type | Notes |
|-----------|--------------|------|-------|
| `date` | తేదీ | `date` | Gregorian date for the city (IST default when query omits `date`) |
| `vaaram` | వారం | `string` | Weekday in `locale` (`సోమవారం` / `Monday`) |
| `tithi` | తిథి | `string` | Lunar day name in `locale` |
| `nakshatram` | నక్షత్రం | `string` | Nakshatra name in `locale` |
| `rahu_kalam` | రాహు కాలం | `{start, end}` | ISO 8601 local datetimes |
| `yama_gandam` | యమగండం | `{start, end}` \| null | Inauspicious window; null when vendor omits |
| `sunrise` | — | `string` | ISO 8601 local datetime |
| `sunset` | — | `string` | ISO 8601 local datetime |

**Vendor JSON → normalized cache (telugu-panchangam-app / `@ishubhamx/panchangam-js` adapter):**

| Vendor path (`data.*`) | `panchangam_daily` / API |
|------------------------|--------------------------|
| `vara.te` / `vara.en` | `vaaram` (pick by `locale`) |
| `tithi.te` / `tithi.en` | `tithi` |
| `nakshatra.te` / `nakshatra.en` | `nakshatram` |
| `rahukalam` | `rahu_kalam` |
| `yamagandam` | `yama_gandam` |
| `sunrise` | `sunrise` |
| `sunset` | `sunset` |
| `yoga.te` / `yoga.en` | `yoga` (optional) |

Worker normalizes nested bilingual objects to a single locale string before upsert.
Clients bind to `GET /v1/panchangam` only — never to vendor shape.

### §23.6.1 — Panchangam integration rules (normative)

Operational rules for vendor wiring, accuracy gate, and launch scope. See
`spec/plans/PANCHANGAM_OPS.md` for runbook.

| Topic | Normative rule |
|-------|----------------|
| **Ayanamsa** | Engine MUST use **Lahiri (Chitrapaksha)** — same as drikpanchang.com default and Indian govt almanac. Pin in adapter; panchangam path does not expose `raman`/`kp` selectors. If reference calendar uses Raman nakshatra, fix adapter (not a runtime toggle). Tithi comparison is ayanamsa-robust; nakshatra comparison assumes Lahiri. Panchang day attributes anchored at **local sunrise** (Udaya Tithi). |
| **City registry** | `app/services/panchangam_cities.py` maps canonical city key → `{lat, lng, tz, display}`. Launch: `hyderabad` only. Unknown city → skip fetch, log warning, no upsert. **Upsert always stores `display` name** (`Hyderabad`); API read stays `lower(city)` match. |
| **Vendor HTTP contract** | Worker calls `GET {PANCHANGAM_VENDOR_URL}?date=&lat=&lng=&tz=Asia/Kolkata&lang=` (telugu-panchangam-app shape). Adapter MUST pass explicit **IST** (`tz=Asia/Kolkata` and/or `timezoneOffset=330` to `panchangam-js`) — never longitude-only timezone guess. `city` is cache key only, never sent to vendor. |
| **Strict upsert (worker)** | Reject cache write unless `tithi`, `nakshatram`, `vaaram`, `sunrise`, `sunset`, `rahu_kalam`, `yama_gandam` all present for Drik Hyderabad launch. Worker invariant only — `yama_gandam` stays **nullable** in API schema (`when present` in CUSTOMER.md). |
| **Beat lock** | `refresh_panchangam_cache_task` acquires Redis `panchangam_refresh_lock` NX EX before fetch (same pattern as `refresh_advance_offers`, `rm_escalation_scan`). |
| **Cache horizon** | Beat pre-fetches **today + 7 days** per city × locale (`te`, `en`) × `drik`. |
| **Accuracy gate** | Of 30 Hyderabad reference dates (`spec/plans/panchangam_reference_hyderabad.csv`): every **non-transition** date must match exactly on `tithi.number`, `nakshatra.number`, and `vaaram`; at most **2 sunrise-boundary (transition) dates** may mismatch. Time fields (rahu, yama, sunrise, sunset): ≥27/30 within tolerance. Reference: **Venkatrama Chitrapaksha Drik** OR manual drikpanchang.com Hyderabad cross-check. Script: `scripts/validate_panchangam_accuracy.py`. **drikpanchang.com is manual ops only** — never scrape in CI (ToS risk); CI uses recorded fixtures. |
| **Tolerance** | Tithi, nakshatram, vaaram: exact. Rahu/yama: ±3 min. Sunrise/sunset: ±2 min. |
| **Launch UI scope** | **Home ribbon** at launch (`C-PANCHANGAM-UI`). **Calendar tab** deferred — needs month view + `GET /v1/panchangam/month` (optional v1.1; derives `auspicious_dates` from cached rows), wider beat horizon (full month+ vs today+7), and an auspicious-date rule (TBD). Track as `C-PANCHANGAM-CALENDAR` PENDING. |
| **Non-goals** | Panchangam does not gate `POST /v1/bookings`, slot holds, or `is_muhurat_bound` logic. Informational UI only. |

### §23.7 — OpenAPI artifact

- Commit `spec/openapi.json` (export from FastAPI when `DEBUG=true`) for Flutter codegen.

### Migration 017 scope

See `spec/db/migration_017.sql` (chains after 016):

- `panchangam_daily` table + unique index on `(city, panchang_date, locale, panchang_system)`

### Migration 018 scope

See `spec/db/migration_018.sql` (chains after 017):

- `panchangam_daily.vaaram TEXT`
- `panchangam_daily.yama_gandam JSONB`
- `panchangam_daily.sunrise TEXT`
- `panchangam_daily.sunset TEXT`
