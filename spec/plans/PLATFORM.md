# Platform track — shared backend

Workers, dispatch, money, auth, infra. Blocks all three apps.

---

## Phase 0 — Integrity (Sprint 1, before dispatch wiring)

### P-DUR-GUARD — Duration snapshot + CHECK constraints
- **Spec:** SPEC_AMENDMENTS.md §12; DATABASE.md migration 006
- **Status:** TODO
- **Files:** `spec/db/migration_006.sql`, `spec/db/triggers.sql`
- **Acceptance:** Trigger 5 uses `NULLIF(duration,0)`; `CHECK (duration_minutes > 0)` on bookings + pujas; backfill before VALIDATE

### P-DIRECT-CLEAR-INTENDED — dispatch-choice guarded conversion
- **Spec:** SPEC_AMENDMENTS.md §13; DISPATCH_FLOW.md §Direct vs broadcast
- **Status:** TODO
- **Files:** `app/api/v1/endpoints/bookings.py`
- **Acceptance:** Guarded UPDATE clears `intended_pujari_id`, sets `dispatch_mode='broadcast'`; 0 rows → 409; then `send_task(broadcast_booking)`

### P-DISPATCH-STATE-RESET — Fresh re-dispatch reset in worker
- **Spec:** SPEC_AMENDMENTS.md §14; DISPATCH_FLOW.md §Dispatch rounds step 0
- **Status:** TODO
- **Files:** `app/workers/dispatch.py`
- **Acceptance:** `rebroadcast_booking(booking_id, fresh=True)` resets round to 0; normal rebroadcast uses `fresh=False`

### P-TXN-LOCK — Mandatory guarded transitions
- **Spec:** SPEC_AMENDMENTS.md §15; DISPATCH_FLOW.md §Guarded transitions
- **Status:** TODO
- **Files:** `app/api/v1/endpoints/service_lifecycle.py`, `bookings.py`, future B-CANCEL
- **Acceptance:** Every state write uses `FOR UPDATE` + guarded `UPDATE … WHERE <predicates>`; 0 rows → 409

---

## Phase 0 — Dispatch blockers (Sprint 1)

### P-REJECT-FAST — Reject fast-path rebroadcast
- **Spec:** DISPATCH_FLOW.md §Fast path on last reject; API_CONTRACTS.md reject endpoint
- **Status:** TODO
- **Files:** `app/services/offer_service.py`, `app/api/v1/endpoints/offers.py`
- **Acceptance:** After reject, if zero live offers remain, `celery_app.send_task("app.workers.dispatch.rebroadcast_booking", ...)`
- **Verify:** Reject last offer → new offers within &lt;2s (Celery running), not 30s sweep wait
- **Depends on:** Celery worker on `dispatch` queue

### P-DISP-CHOICE — Customer broadcast choice enqueue
- **Spec:** API_CONTRACTS.md `dispatch-choice`; DISPATCH_FLOW.md direct miss; SPEC_AMENDMENTS.md §13
- **Status:** TODO
- **Files:** `app/api/v1/endpoints/bookings.py`
- **Acceptance:** `action=broadcast` → guarded UPDATE (P-DIRECT-CLEAR-INTENDED) → `send_task(broadcast_booking)` after commit. `action=cancel` → existing `cancellation_service` (requested → cancelled, 100% refund); no second cancel implementation.
- **Verify:** Customer opts broadcast → dispatch starts without sweep

### P-DISP-DIRECT — Direct dispatch mode
- **Spec:** DISPATCH_FLOW.md §Direct vs broadcast
- **Status:** TODO
- **Files:** `app/workers/dispatch.py` (new `_direct_dispatch` path)
- **Acceptance:** `dispatch_mode='direct'` → single offer to `intended_pujari_id`, `expires_at = now() + 10 min`; no geo rounds until customer opts broadcast
- **Verify:** Named-pujari booking → exactly one offer to that pujari

### P-WEBHOOK-BRANCH — Webhook enqueue branch
- **Spec:** DISPATCH_FLOW.md lifecycle step 4–5
- **Status:** TODO
- **Files:** `app/api/v1/endpoints/webhooks.py`, `app/services/webhook_service.py`
- **Acceptance:** Return `enqueue_direct` vs `enqueue_broadcast` from webhook service based on `bookings.dispatch_mode`
- **Depends on:** P-DISP-DIRECT

### P-DISP-PRICING — Puja eligibility filter
- **Spec:** DISPATCH_FLOW.md dispatch step 3 (puja match)
- **Status:** TODO
- **Files:** `app/workers/dispatch.py`, `app/api/v1/endpoints/catalog.py`
- **Acceptance:** Join `pujari_pricing` on `(pujari_id, puja_id)` — **not** `pujari_pujas` (table does not exist)
- **Verify:** Pujari without pricing row for puja never offered

---

## Foundation (done / partial)

### P-DB — Database migrations
- **Spec:** DATABASE.md
- **Status:** DONE
- **Files:** `migrations/versions/001`–`004`, `spec/db/*.sql`

### P-EXC — Exception handler
- **Spec:** API_CONTRACTS.md error table
- **Status:** DONE
- **Files:** `app/core/exceptions.py`

### P-REDIS — Redis client
- **Spec:** ARCHITECTURE.md Redis section
- **Status:** DONE
- **Files:** `app/core/redis_client.py`, `app/main.py`

### P-AUTH — Authentication
- **Spec:** API_CONTRACTS.md §Auth
- **Status:** PARTIAL (MSG91 stub — logs OTP in DEBUG)
- **Files:** `app/api/v1/endpoints/auth.py`
- **Next:** P-NOTIFY MSG91 integration for OTP send

### P-CTX — app_context
- **Spec:** project.mdc, API_CONTRACTS.md
- **Status:** DONE
- **Files:** `app/core/dependencies.py`

### P-WS — WebSocket
- **Spec:** API_CONTRACTS.md §WS, ARCHITECTURE.md rule 6
- **Status:** PARTIAL
- **Files:** `app/api/v1/endpoints/ws.py`
- **Next:** Server publishes structured events (status change, pujari location) to `booking:{id}`

### P-SWEEP — Sweep worker
- **Spec:** DISPATCH_FLOW.md §Expiry, abandonment, and re-broadcast
- **Status:** DONE
- **Files:** `app/workers/sweep.py`, `app/workers/celery_app.py`

### P-REFUND — Refund worker
- **Spec:** DISPATCH_FLOW.md §Refund execution; project.mdc rule 4
- **Status:** DONE (live Razorpay verification pending)
- **Files:** `app/workers/refund.py`

### P-DISP-BROADCAST — Broadcast rounds
- **Spec:** DISPATCH_FLOW.md §Dispatch rounds
- **Status:** PARTIAL (missing P-DISP-PRICING)
- **Files:** `app/workers/dispatch.py`

---

## Phase 3 — Money (hard-blocked until P-GST-MODEL)

### P-GST-MODEL — GST / TCS settlement model
- **Spec:** SPEC_AMENDMENTS.md §16; MASTER.md Phase 3 exit gate
- **Status:** BLOCKED — tax advisor sign-off required
- **Acceptance:** Documented decision on GST base, TCS obligation, unregistered pujaris, `net_pujari_amount` formula

### P-SPLIT-CONFIG — Platform fee + GST settings
- **Spec:** DATABASE.md `platform_settings`
- **Status:** BLOCKED — depends on P-GST-MODEL
- **Acceptance:** Seed + admin APIs for `commission_pct`, `gst_pct` (same pattern as advance)

### P-SPLITS — payment_splits insert
- **Spec:** DISPATCH_FLOW.md step 8 SETTLEMENT; DATABASE.md
- **Status:** BLOCKED — depends on P-GST-MODEL, P-SPLIT-CONFIG
- **Files:** `app/services/webhook_service.py` (on payment success)
- **Acceptance:** INSERT `payment_splits` row; trigger 1 computes `net_pujari_amount` from `platform_fee` + `gst_amount` on `payments.amount` (= `amount_due_online`)

### P-REFUND-CAP — Total refund cap
- **Spec:** DATABASE.md migration 005; SPEC_AMENDMENTS.md §2
- **Status:** TODO
- **Files:** `spec/db/migration_005.sql` (new), refund insert paths
- **Acceptance:** DDL in `spec/db/migration_005.sql` exists; apply on dev DB + integration test that sequential refunds cannot exceed `payments.amount`

### P-PAYOUT — Payouts worker
- **Spec:** ARCHITECTURE.md stack table; DISPATCH_FLOW.md settlement
- **Status:** TODO
- **Depends on:** P-SPLITS

---

## Phase 2 — Notifications

### P-NOTIFY — FCM + MSG91
- **Spec:** DISPATCH_FLOW.md step 5; ARCHITECTURE.md
- **Status:** TODO (stub)
- **Files:** `app/workers/notifications.py`

---

## Infra / ops

### P-ADMIN-ROLE — Admin role check
- **Spec:** API_CONTRACTS.md §Admin; SPEC_AMENDMENTS.md
- **Status:** TODO
- **Files:** `app/core/dependencies.py` — verify `user_roles` not only `app_context=admin`

### P-PGBOUNCER — Prepared statement config
- **Spec:** ARCHITECTURE.md connection policy; STACK_VERSIONS.md psycopg3
- **Status:** TODO
- **Files:** `app/db/engine.py` — `connect_args={"prepare_threshold": None}`

### P-MONITOR — Stuck-state alerts
- **Spec:** ARCHITECTURE.md monitoring; SPEC_AMENDMENTS.md §6
- **Status:** TODO
- **Acceptance:** Alert on payment_pending past hold+grace, confirmed past scheduled_time without start, refunds pending beyond N retries

---

## Phase 5 — Post-MVP ops (SPEC_AMENDMENTS)

### P-SWEEP-CONFIRMED — Stuck confirmed bookings
- **Spec:** SPEC_AMENDMENTS.md §3; DISPATCH_FLOW.md (new section)
- **Status:** TODO

### P-RECONFIRM — Pre-event reconfirmation
- **Spec:** SPEC_AMENDMENTS.md §4
- **Status:** TODO

### P-PLL-GEOM — Optional pll geom sync trigger
- **Spec:** SPEC_AMENDMENTS.md review log; DISPATCH_FLOW.md §Presence
- **Status:** TODO (P2, migration 007 — not bundled in 006)
- **Note:** Heartbeat is the sole `pujari_live_location.geom` writer at launch
