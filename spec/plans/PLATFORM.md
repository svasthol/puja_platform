# Platform track — shared backend

Workers, dispatch, money, auth, infra. Blocks all three apps.

> **Status lives in `STATUS.md` — the single source of truth for implementation progress.**
> Track files define scope only: Spec / Files / Acceptance / Depends-on. Never add a
> `Status:` field here; it will drift.

---

## Phase 0 — Integrity (Sprint 1, before dispatch wiring)

### P-DUR-GUARD — Duration snapshot + CHECK constraints
- **Spec:** SPEC_AMENDMENTS.md §12; DATABASE.md migration 006
- **Files:** `spec/db/migration_006.sql`, `spec/db/triggers.sql`
- **Acceptance:** Trigger 5 uses `NULLIF(duration,0)`; `CHECK (duration_minutes > 0)` on bookings + pujas; backfill before VALIDATE

### P-DIRECT-CLEAR-INTENDED — dispatch-choice guarded conversion
- **Spec:** SPEC_AMENDMENTS.md §13; DISPATCH_FLOW.md §Direct vs broadcast
- **Files:** `app/api/v1/endpoints/bookings.py`
- **Acceptance:** Guarded UPDATE clears `intended_pujari_id`, sets `dispatch_mode='broadcast'`; 0 rows → 409; then `send_task(broadcast_booking)`

### P-DISPATCH-STATE-RESET — Fresh re-dispatch reset in worker
- **Spec:** SPEC_AMENDMENTS.md §14; DISPATCH_FLOW.md §Dispatch rounds step 0
- **Files:** `app/workers/dispatch.py`
- **Acceptance:** `rebroadcast_booking(booking_id, fresh=True)` resets round to 0; normal rebroadcast uses `fresh=False`

### P-TXN-LOCK — Mandatory guarded transitions
- **Spec:** SPEC_AMENDMENTS.md §15; DISPATCH_FLOW.md §Guarded transitions
- **Files:** `app/api/v1/endpoints/service_lifecycle.py`, `bookings.py`, future B-CANCEL
- **Acceptance:** Every state write uses `FOR UPDATE` + guarded `UPDATE … WHERE <predicates>`; 0 rows → 409

---

## Phase 0 — Dispatch blockers (Sprint 1)

### P-REJECT-FAST — Reject fast-path rebroadcast
- **Spec:** DISPATCH_FLOW.md §Fast path on last reject; API_CONTRACTS.md reject endpoint
- **Files:** `app/services/offer_service.py`, `app/api/v1/endpoints/offers.py`
- **Acceptance:** After reject, if zero live offers remain, `celery_app.send_task("app.workers.dispatch.rebroadcast_booking", ...)`
- **Verify:** Reject last offer → new offers within &lt;2s (Celery running), not 30s sweep wait
- **Depends on:** Celery worker on `dispatch` queue

### P-DISP-CHOICE — Customer broadcast choice enqueue
- **Spec:** API_CONTRACTS.md `dispatch-choice`; DISPATCH_FLOW.md direct miss; SPEC_AMENDMENTS.md §13
- **Files:** `app/api/v1/endpoints/bookings.py`
- **Acceptance:** `action=broadcast` → guarded UPDATE (P-DIRECT-CLEAR-INTENDED) → `send_task(broadcast_booking)` after commit. `action=cancel` → existing `cancellation_service` (requested → cancelled, 100% refund); no second cancel implementation.
- **Verify:** Customer opts broadcast → dispatch starts without sweep

### P-DISP-DIRECT — Direct dispatch mode
- **Spec:** DISPATCH_FLOW.md §Direct vs broadcast
- **Files:** `app/workers/dispatch.py` (new `_direct_dispatch` path)
- **Acceptance:** `dispatch_mode='direct'` → single offer to `intended_pujari_id`, `expires_at = now() + 10 min`; no geo rounds until customer opts broadcast
- **Verify:** Named-pujari booking → exactly one offer to that pujari

### P-WEBHOOK-BRANCH — Webhook enqueue branch
- **Spec:** DISPATCH_FLOW.md lifecycle step 4–5
- **Files:** `app/api/v1/endpoints/webhooks.py`, `app/services/webhook_service.py`
- **Acceptance:** Return `enqueue_direct` vs `enqueue_broadcast` from webhook service based on `bookings.dispatch_mode`
- **Depends on:** P-DISP-DIRECT

### P-DISP-PRICING — Puja eligibility filter
- **Spec:** DISPATCH_FLOW.md dispatch step 3 (puja match)
- **Files:** `app/workers/dispatch.py`, `app/api/v1/endpoints/catalog.py`
- **Acceptance:** Join `pujari_pricing` on `(pujari_id, puja_id)` — **not** `pujari_pujas` (table does not exist)
- **Verify:** Pujari without pricing row for puja never offered

---

## Foundation

### P-DB — Database migrations
- **Spec:** DATABASE.md
- **Files:** `migrations/versions/001`–`004`, `spec/db/*.sql`

### P-EXC — Exception handler
- **Spec:** API_CONTRACTS.md error table
- **Files:** `app/core/exceptions.py`

### P-REDIS — Redis client
- **Spec:** ARCHITECTURE.md Redis section
- **Files:** `app/core/redis_client.py`, `app/main.py`

### P-AUTH — Authentication
- **Spec:** API_CONTRACTS.md §Auth; SPEC_AMENDMENTS.md §17
- **Files:** `app/api/v1/endpoints/auth.py`, `app/services/sms_router.py`
- **Acceptance:** `POST /v1/auth/otp/request` → `sms_router` failover; response includes `sms_sent`, `sms_provider`; DEBUG fallback when all providers fail

### P-SMS-ROUTER — Multi-provider SMS failover
- **Spec:** SPEC_AMENDMENTS.md §17; ARCHITECTURE.md §SMS
- **Files:** `sms_router.py`, `fast2sms_client.py`, `msg91_client.py`, `sms_phone.py`
- **Acceptance:** `SMS_PROVIDER_ORDER` chain; `MSG91_ENABLED=false` skips MSG91 until DLT; tests in `test_sms_router.py`

### P-CTX — app_context
- **Spec:** project.mdc, API_CONTRACTS.md
- **Files:** `app/core/dependencies.py`

### P-WS — WebSocket
- **Spec:** API_CONTRACTS.md §WS, ARCHITECTURE.md rule 6
- **Files:** `app/api/v1/endpoints/ws.py`, `app/services/booking_events.py`
- **Done:** Server publishes `status_changed` to `booking:{id}` on payment confirmed + offer accept
- **Next:** Pujari location events on heartbeat; richer event schema for Flutter

### P-SWEEP — Sweep worker
- **Spec:** DISPATCH_FLOW.md §Expiry, abandonment, and re-broadcast
- **Files:** `app/workers/sweep.py`, `app/workers/celery_app.py`

### P-REFUND — Refund worker
- **Spec:** DISPATCH_FLOW.md §Refund execution; project.mdc rule 4
- **Files:** `app/workers/refund.py`
- **Note:** Live Razorpay verification pending (Phase 3)

### P-DISP-BROADCAST — Broadcast rounds
- **Spec:** DISPATCH_FLOW.md §Dispatch rounds
- **Files:** `app/workers/dispatch.py`

---

## Sprint 4-0 — Security hotfix (P0 — NOT Phase 3, NOT on hold)

**These five tasks are Phase 4-0 and ship before any admin surface.** They are listed
here (not only in `ADMIN.md`) because they live in shared platform files —
`auth.py`, `security.py`, `dependencies.py` — and `P-AUTH-FIX` affects customer and
pujari apps too. The Phase 3 hold below does **not** apply to them.

**Migration 009 ships in this sprint** (not 4A) — `P-AUTH-FIX`, `P-ADMIN-SEED`, and
`P-ADMIN-AUTH` all need its DDL. **Build order:** `P-ADMIN-AUTH-FIX` → migration 009 →
`P-AUTH-FIX` → `P-ADMIN-SEED` → `P-ADMIN-ROLE` → `P-ADMIN-AUTH` (SEED before ROLE —
role rows must exist before anything checks them).

### P-ADMIN-AUTH-FIX — Close admin OTP escalation vector
- **Spec:** SPEC_AMENDMENTS.md §19.1; `API_CONTRACTS.md` §Auth
- **Priority:** **P0** (Sprint 4-0)
- **Files:** `app/schemas/auth.py`, `app/api/v1/endpoints/auth.py`
- **Problem (verified):** `app_context` on `otp_verify` is a **query parameter** (bare scalar
  default). Any phone passing OTP can request `?app_context=admin` with no role check; claim
  lands in access logs. User is auto-created if missing.
- **Acceptance:** `app_context` is a **body field** on `OtpVerify` (`customer` | `pujari` only
  for SMS path). Admin tokens never issued via SMS OTP (see `P-ADMIN-AUTH` TOTP). Pair with
  `P-ADMIN-ROLE` issuance + dependency checks.

### P-AUTH-FIX — Refresh/logout lookup + OTP lockout persistence
- **Spec:** SPEC_AMENDMENTS.md §19.1; `API_CONTRACTS.md` §Auth
- **Priority:** **P0** (Sprint 4-0; affects customer/pujari/admin)
- **Files:** `app/api/v1/endpoints/auth.py`, `app/core/security.py`, migration **009**
  (`auth_sessions.refresh_jti` or equivalent)
- **Problem (verified in code):**
  1. `refresh` / `logout` look up `auth_sessions` by `refresh_token_hash == hash_secret(token)`.
     `hash_secret` uses `bcrypt.gensalt()` → different digest every call → lookup always fails
     (refresh 401, logout silent no-op). OTP verify correctly uses `verify_secret`.
  2. Failed OTP: `row.attempts += 1` then `raise` inside `get_db_txn` → transaction rolls back
     → attempts never persist; only Redis 10/hour limit is real.
- **Acceptance:**
  - Store refresh `jti` from JWT on `auth_sessions`; lookup by `jti`, verify token with
    `verify_secret` against `refresh_token_hash` (rotation + logout).
  - OTP failures persist attempt count (Redis counter or autonomous write outside the verify txn).
  - Tests: refresh rotation, logout revokes session, 5th bad OTP rejects without new request.

### P-ADMIN-ROLE — Admin role check
- **Spec:** API_CONTRACTS.md §Auth; SPEC_AMENDMENTS.md §8, §19
- **Priority:** **P0 hotfix** (Sprint 4-0)
- **Files:** `app/core/dependencies.py`, `app/api/v1/endpoints/auth.py`
- **Acceptance:** Refuse `app_context=admin` at OTP verify without `user_roles`; `require_admin` loads roles
- **Scoping (implementation trap):** load/check `user_roles` **only when `app_context=admin`**.
  A global role check in `get_principal` would 403 every existing customer and pujari —
  none of them have `user_roles` rows.
- **Depends on:** `P-ADMIN-SEED` (role rows must exist); ships with `P-ADMIN-AUTH-FIX`, `P-AUTH-FIX`

### P-ADMIN-SEED — Roles seed + first-admin bootstrap
- **Spec:** SPEC_AMENDMENTS.md §19; migration **009**
- **Priority:** **P0** (Sprint 4-0)
- **Acceptance:** Seed `roles` (`admin`, `support`); env-keyed first-admin bootstrap script;
  `POST /v1/admin/users/{id}/roles` for subsequent assignments. See `ADMIN.md`.

### P-ADMIN-AUTH — Admin login without SMS OTP
- **Spec:** SPEC_AMENDMENTS.md §19; `API_CONTRACTS.md` §Auth
- **Priority:** **P0** (Sprint 4-0 exit gate)
- **Acceptance:** TOTP (Google Authenticator) or email magic-link for staff; admin refresh TTL
  ≤ 1 day; credential storage in migration 009 — TOTP secrets are **encrypted, never hashed**
  (verification needs the plaintext; see SPEC_AMENDMENTS §19 TOTP storage). One-time
  **self-enrolment on first admin login** for role-holders without a credential (closes the
  first-admin lockout — see `ADMIN.md` P-ADMIN-SEED). See `ADMIN.md`.

---

## Phase 3 — Money / tax (SPEC_AMENDMENTS §16 v1.2)

**Gates before prod money:** (0) Razorpay Route confirmed · (1) CA memo → `advisor_signoff_ref` ·
(2) migration 007 DDL applied · (3) statutory **seed** from memo.

**Phase 3 ON HOLD** — do not implement checkout snapshot or payout until CA approves.
(Does **not** apply to Sprint 4-0 above or to `P-REFUND-CAP`, which is already shipped.)

### P-GST-MODEL — CA signed memo
- **Spec:** SPEC_AMENDMENTS.md §16; GST model v1.2 §11
- **Blocked-by:** CA memo — `advisor_signoff_ref` required to seed `tax_statutory_config`
- **Acceptance:** Signed memo answering 17 questions; Q15 aggregate turnover first

### P-SPLIT-CONFIG — Tax config tables
- **Spec:** DATABASE.md migration 007; A-TAX-CONFIG.md
- **Note:** **DDL unblocked** (no CA memo needed for `CREATE TABLE`); **statutory INSERT** blocked on memo
- **Acceptance:** `tax_statutory_config` (migrate role only) + `tax_commercial_config` (app INSERT only); `v_tax_config_current` view

### P-SPLITS — payment_splits on webhook
- **Spec:** DISPATCH_FLOW.md step 8; §16
- **Acceptance:** INSERT splits from **snapshotted** `tax_*_config_id` on booking; `Decimal` math; IGST branch when interstate

### P-TDS-393 — Income-tax withholding (s.393)
- **Spec:** §16; GST model v1.2 §9
- **Priority:** **P0** — not gated on GST memo
- **Acceptance:** FY counters, recoverable ledger, Form 140/131 paths; TAN required

### P-RAZORPAY-ROUTE — Split settlement
- **Spec:** GST model v1.2 §15
- **Priority:** **P0**
- **Acceptance:** Written confirmation Route enabled; pujari funds not retained as platform revenue

### P-IGST — Place of supply
- **Spec:** §16
- **Blocked-by:** `billing_state_code` (C-ADDR)

### P-INVOICE-SERIES — Tax invoices / consolidated daily
- **Spec:** GST model v1.2 §8; Q16

### P-REFUND-CAP — Total refund cap
- **Spec:** DATABASE.md migration 005; §16 Example F
- **Acceptance:** `trg_refunds_cap_total`: `SUM(succeeded refunds) + new.amount <= payments.amount`
  (verified on dev DB at Alembic 006). `payments.amount` equals `amount_due_online` /
  `total_charged_online` post-Phase-3 — correct cap target in both eras.
- **Verify:** `python scripts/check_migration_005.py`

### P-PAYOUT — Payouts worker
- **Spec:** DISPATCH_FLOW.md settlement
- **Depends on:** P-SPLITS, P-RAZORPAY-ROUTE

---

## Phase 2 — Notifications

**Sprint 2 order:** P-SMS-ROUTER → P-AUTH → P-NOTIFY → B-DEVICE (PARTNER.md) → P-WS partial.
See task definitions above (`P-SMS-ROUTER`, `P-AUTH`, `P-WS`). **Exit gate (SPEC_AMENDMENTS §18):**
live SMS requires DLT registration (even for testing); live FCM requires Flutter device registration.
Until then, backend Phase 2 code is considered complete; use `DEBUG` OTP fallback for dev flows.

### P-NOTIFY — FCM + SMS fallback
- **Spec:** DISPATCH_FLOW.md step 5; ARCHITECTURE.md; SPEC_AMENDMENTS.md §17
- **Files:** `app/workers/notifications.py`, `app/services/fcm_client.py`
- **Acceptance:** `notify_offers` / `notify_no_pujari` Celery tasks; FCM 3-attempt retry; UNREGISTERED deletes `devices` row; direct-offer SMS via `sms_router`; inserts `notifications` audit rows
- **Verify:** Celery worker on `notifications` queue; `pytest tests/test_phase2_notifications.py`

### P-NOTIFY env (SMS subset)

See SPEC_AMENDMENTS §17. Launch default:

```bash
SMS_PROVIDER_ORDER=fast2sms,msg91
MSG91_ENABLED=false
FAST2SMS_API_KEY=<dev api key>
```

---

## Infra / ops

### P-EXC-ADMIN-PATHS — Exception handler admin/webhook branching
- **Spec:** `API_CONTRACTS.md` error table
- **Priority:** **P1** (Sprint 4C — before `A-REFUND`, `A-REASSIGN`)
- **Files:** `app/core/exceptions.py`
- **Problem:** `ux_refunds_one_active_per_payment` always returns 200; admin needs 409.
  `ex_bookings_pujari_no_overlap` always returns pujari copy; admin reassign needs its own message.
- **Acceptance:** Branch on `"/admin/" in path` (mirror existing `"/webhooks/"` pattern).

### P-PGBOUNCER — Prepared statement config
- **Spec:** ARCHITECTURE.md connection policy; STACK_VERSIONS.md psycopg3
- **Files:** `app/db/engine.py` — `connect_args={"prepare_threshold": None}`

### P-MONITOR — Stuck-state alerts (M0 foundation)
- **Spec:** `ARCHITECTURE.md` monitoring; `SPEC_AMENDMENTS.md` §10; **`spec/OBSERVABILITY.md`**
- **Acceptance:** Alert on payment_pending past hold+grace, confirmed past scheduled_time without start, refunds pending beyond N retries; `/metrics` + `ops_monitor_alerts`
- **Phase 7 extension:** `spec/plans/OBSERVABILITY.md` (`M-LIFECYCLE-*`, `M-BOOKING-NOTIFY`, `M-HEALTH-*`, `M-SYNTHETIC-PROBE`) — **blocked until app design complete**

---

## Flutter backend contract (SPEC_AMENDMENTS §23)

**Policy:** [`API_CONTRACTS.md`](../API_CONTRACTS.md) v3.4. **Blocks** Flutter codegen + tracking UX.
**Status:** spec **DONE** (2026-07-29); implementation **PENDING** in `STATUS.md`.

| ID | Scope | Acceptance |
|---|---|---|
| **P-APP-CONFIG** | `app/api/v1/endpoints/app_config.py` | Public `GET /v1/app-config` from `platform_settings` |
| **P-FLUTTER-CONTRACT** | `bookings.py`, `catalog_read.py`, schemas | `booking_class` on C-GET/list + create; `is_muhurat_bound` on catalog |
| **P-RECONFIRM-API** | `pujari_bookings.py` or `service_lifecycle.py` | `POST /v1/pujari/bookings/{id}/reconfirm` idempotent |
| **P-PANCHANGAM-API** | mig 017–018 + endpoint | `GET /v1/panchangam` reads `panchangam_daily` (contract shell — **COMPLETED**) |
| **P-PANCHANGAM-VENDOR** | worker + `panchangam_cities` | lat/lng vendor fetch, strict upsert, beat lock — **COMPLETED** |
| **P-PANCHANGAM-ACCURACY** | validation script + reference CSV | Venkatrama gate — **COMPLETED** |
| **P-PANCHANGAM-DEPLOY** | engine host + env | dev same-host; prod separate EC2/Docker — **PENDING** |
| **P-PANCHANGAM-LAUNCH-GATE** | ops sign-off | `PANCHANGAM_OPS.md` checklist — **PENDING** |
| **C-PANCHANGAM-UI** | Flutter customer ribbon | **HOLD** — code scaffolded; align + QA when `C-FLUTTER-CUSTOMER` starts |
| **C-PANCHANGAM-CALENDAR** | Flutter calendar tab | post-launch — **PENDING** |
| **P-OPENAPI-ARTIFACT** | `spec/openapi.json` | Export on contract change; Flutter `openapi_generator` |

**Execution sequence:** SPEC_AMENDMENTS §23.6.1 → Phase 1 Venkatrama gate → vendor wiring →
accuracy CI → deploy → Flutter ribbon (`C-PANCHANGAM-UI`) → launch gate. Calendar tab deferred.

---

## Phase 5 — Post-MVP ops (SPEC_AMENDMENTS)

### P-SWEEP-CONFIRMED — Stuck confirmed bookings
- **Spec:** SPEC_AMENDMENTS.md §3; DISPATCH_FLOW.md (new section)

### P-RECONFIRM — Pre-event reconfirmation
- **Spec:** SPEC_AMENDMENTS.md §4, §21.7
- **Launch:** **Mandatory** for advance bookings (≥24h lead)

### P-PLL-GEOM — Optional pll geom sync trigger
- **Spec:** SPEC_AMENDMENTS.md review log; DISPATCH_FLOW.md §Presence
- **Priority:** P2 — migration **008** (007 is tax)
- **Note:** Phase 2 geo dispatch; launch heartbeat does not require geom (§21.2)

---

## Puja MVP launch (SPEC_AMENDMENTS §21) — implementation track

**Policy docs:** `LAUNCH_POLICY.md`, `DISPATCH_FLOW.md` §Puja MVP launch dispatch.
**Migration:** 012 (planned). **Ship heartbeat + dispatch changes in one PR.**

| ID | Scope | Acceptance |
|---|---|---|
| **P-LAUNCH-NO-DIRECT** | API/UI | No `pujari_id` on holds/bookings; `dispatch-choice` returns 404/410; no `direct_dispatch` enqueue. **Do not drop** `intended_pujari_id` / constraints. |
| **P-LAUNCH-DISPATCH** | `workers/dispatch.py` | Citywide eligibility; no `ST_DWithin`; `dispatch_starts_at` / `dispatch_deadline`; status-aware re-offer |
| **P-LAUNCH-HEARTBEAT** | `pujaris.py` | Optional `{lat,lng}`; presence-only launch path |
| **P-LAUNCH-BUFFER** | dispatch + accept | Soft `dispatch_buffer_minutes` (default 60) — not in exclusion constraint |
| **P-LAUNCH-AREA** | addresses API | `service_area_id` required; `GET /service-areas` |
| **P-LAUNCH-RM** | admin + booking APIs | `relationship_managers` CRUD; expose on customer/pujari booking after confirm |
| **P-LAUNCH-PUJARI-BOOKING** | pujari endpoints | `GET /pujari/bookings`, `GET /pujari/bookings/{id}` — address + map, no customer phone |
| **P-LAUNCH-OFFERS** | offers list | `area_label`, puja, schedule on offer cards |
| **P-LAUNCH-RECONFIRM** | worker + notify | Mandatory 24h ping for advance bookings (§21.7) |
| **C-LAUNCH-UX** | Flutter (`P-FLUTTER-PARTNER`) | **IN_PROGRESS** — not started; backend ready. Offers vs Bookings tabs; go online without GPS |
| **C-FLUTTER-CUSTOMER** | Flutter (separate repo) | **IN_PROGRESS** — not started; backend ready. Full customer launch UX (§21) |
