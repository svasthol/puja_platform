# Development status tracker

**Single source of truth for implementation progress.** Update this file in the same
change as every completed task. Details and acceptance criteria: track files
(`PLATFORM.md`, `CUSTOMER.md`, `PARTNER.md`, `ADMIN.md`). Phase order and exit
gates: [`MASTER.md`](./MASTER.md).

**Last audited:** 2026-07-12 (Phase 1 code) · **pytest:** 17 passed

---

## Status vocabulary (use exactly one per row)

| Status | Meaning | When to use |
|---|---|---|
| **COMPLETED** | Done; acceptance criteria met | Code merged + verified |
| **IN_PROGRESS** | Actively being worked this sprint | Someone owns it now |
| **PENDING** | Not started; on the roadmap | Default for planned work |
| **BLOCKED** | Cannot start until dependency resolves | Note `blocked_by` in Notes |
| **SKIPPED** | Explicitly out of scope for this release | Note reason (product/policy) |

**Phase rule:** A phase is **COMPLETED** only when every task in that phase is
`COMPLETED` or `SKIPPED`, all `BLOCKED` items are unblocked and done, and the
exit gate in MASTER.md is met.

---

## Phase dashboard

| Phase | Name | Phase status | Exit gate (summary) |
|---|---|---|---|
| **0** | Integrity + dispatch | **COMPLETED** | P0 trio + dispatch wiring + Sprint 1 concurrency tests |
| **0.5** | Supply onboarding | **IN_PROGRESS** | KYC approve path; earnings stub |
| **1** | Customer + partner APIs | **COMPLETED** | Addresses, booking detail, availability |
| **2** | Notifications | **PENDING** | MSG91 OTP + FCM offer push |
| **3** | Money pipeline | **BLOCKED** | P-GST-MODEL sign-off → splits, refund cap, payouts |
| **4** | Admin ops | **PENDING** | Search, reassign, refund queue |
| **5** | Scheduled-booking ops | **PENDING** | Pujari cancel, stuck-confirmed sweep |
| **6** | Launch gate | **PENDING** | Full DISPATCH_FLOW concurrent test suite green |

---

## Phase 0 — Integrity + dispatch (Sprint 1)

### P0 integrity

| ID | Status | Notes |
|---|---|---|
| P-DUR-GUARD | COMPLETED | migration_006.sql + Alembic 006; apply on dev DB |
| P-DIRECT-CLEAR-INTENDED | COMPLETED | dispatch-choice guarded UPDATE + clear intended |
| P-DISPATCH-STATE-RESET | COMPLETED | `rebroadcast_booking(..., fresh=True)` under lock |
| P-TXN-LOCK | COMPLETED | guarded UPDATE + `StaleBookingState` on start/complete/dispatch-choice/cancel |

### Dispatch wiring

| ID | Status | Notes |
|---|---|---|
| P-REJECT-FAST | COMPLETED | offers reject → `send_task(rebroadcast)` |
| P-DISP-CHOICE | COMPLETED | broadcast enqueue + cancel → cancellation_service |
| P-DISP-DIRECT | COMPLETED | `direct_dispatch` task, 10 min expiry |
| P-WEBHOOK-BRANCH | COMPLETED | direct vs broadcast enqueue |
| P-DISP-PRICING | COMPLETED | `pujari_pricing` join in dispatch |
| P-DISP-BROADCAST | COMPLETED | geo rounds + pricing filter |

### Sprint 1 concurrency tests (alongside code — not Phase 6 only)

| Test | Status | Notes |
|---|---|---|
| LG-fresh-dispatch | COMPLETED | `test_fresh_rebroadcast_resets_round_to_one` |
| LG-cancel-vs-start | COMPLETED | `test_start_then_cancel_guard_fails` |
| LG-dispatch-choice-race | COMPLETED | `test_dispatch_choice_guard_second_update_gets_zero_rows` + StaleBookingState unit test |

---

## Platform (all phases)

| ID | Status | Phase | Notes |
|---|---|---|---|
| P-DB | COMPLETED | — | migrations 001–004 + triggers + seed |
| P-EXC | COMPLETED | — | shared DB exception handler |
| P-REDIS | COMPLETED | — | lifespan + reconnect |
| P-CTX | COMPLETED | — | app_context enforcement |
| P-SWEEP | COMPLETED | — | 5-step sweep + rebroadcast enqueue |
| P-REFUND | COMPLETED | — | refund worker (live Razorpay TBD) |
| P-AUTH | IN_PROGRESS | 2 | OTP works; MSG91 stub |
| P-WS | IN_PROGRESS | 2 | relay only; no server events |
| P-REFUND-CAP | IN_PROGRESS | 3 | DDL in migration_005; apply + verify |
| P-NOTIFY | PENDING | 2 | FCM + MSG91 workers |
| P-ADMIN-ROLE | PENDING | 4 | user_roles check |
| P-PGBOUNCER | PENDING | — | prepare_threshold=None |
| P-MONITOR | PENDING | 5 | stuck-state alerts |
| P-GST-MODEL | BLOCKED | 3 | blocked_by: tax advisor sign-off |
| P-SPLIT-CONFIG | BLOCKED | 3 | blocked_by: P-GST-MODEL |
| P-SPLITS | BLOCKED | 3 | blocked_by: P-GST-MODEL, P-SPLIT-CONFIG |
| P-PAYOUT | PENDING | 3 | blocked_by: P-SPLITS |
| P-SWEEP-CONFIRMED | PENDING | 5 | stuck confirmed / no-show |
| P-RECONFIRM | SKIPPED | 5 | post-MVP default (SPEC_AMENDMENTS §4) |
| P-PLL-GEOM | PENDING | — | P2 optional; migration 007 |

---

## Customer

| ID | Status | Phase | Notes |
|---|---|---|---|
| C-QUOTE | COMPLETED | — | checkout quote |
| C-HOLD | COMPLETED | — | slot holds |
| C-BOOK | COMPLETED | — | bookings + idempotent 409 |
| C-CANCEL | COMPLETED | — | customer cancel |
| C-PUJAS | COMPLETED | 1 | keyset cursor on (name, id) |
| C-PUJARIS | COMPLETED | 1 | `pujari_pricing` join + base_price + cursor |
| C-GET | COMPLETED | 1 | full detail: pujari, history, refund, address |
| C-DISPATCH-CHOICE | COMPLETED | guarded broadcast + celery enqueue |
| C-WS | IN_PROGRESS | 2 | socket relay only |
| C-LIST | COMPLETED | 1 | `GET /v1/bookings` keyset (created_at, id) |
| C-ADDR | COMPLETED | 1 | addresses.py CRUD; geom via trigger (mig 005) |
| C-PROMO | COMPLETED | 1 | atomic counter upsert + redemption in checkout txn |
| C-PAGINATION | COMPLETED | 1 | encode/decode_cursor in schemas/common.py |

---

## Partner (pujari)

| ID | Status | Phase | Notes |
|---|---|---|---|
| B-OFFERS | COMPLETED | — | GET offers |
| B-ACCEPT | COMPLETED | — | accept race |
| B-HEARTBEAT | COMPLETED | — | presence + geom |
| B-START | COMPLETED | — | start service |
| B-BALANCE | COMPLETED | — | balance collected ack |
| B-COMPLETE | COMPLETED | — | complete service |
| B-REJECT | COMPLETED | reject + P-REJECT-FAST celery enqueue |
| B-EARNINGS | BLOCKED | 3 | blocked_by: P-SPLITS |
| B-AVAIL | COMPLETED | 1 | `PUT/GET /v1/me/availability` replace-all |
| B-UNAVAIL | COMPLETED | 1 | `PUT/GET /v1/me/unavailability` replace-all |
| B-KYC | IN_PROGRESS | 0.5 | KYC vendor staging research underway |
| B-DEVICE | PENDING | 2 | FCM device token |
| B-CANCEL | PENDING | 5 | pujari-cancel (SPEC_AMENDMENTS) |
| B-REGISTER | PENDING | 0.5 | profile bootstrap |

---

## Admin

| ID | Status | Phase | Notes |
|---|---|---|---|
| A-ADVANCE | COMPLETED | — | advance booking amount |
| A-COMMISSION | BLOCKED | 3 | blocked_by: P-GST-MODEL |
| A-KYC | PENDING | 0.5 | KYC review queue |
| A-SEARCH | PENDING | 4 | booking search |
| A-REASSIGN | PENDING | 4 | manual reassign |
| A-REFUND | PENDING | 4 | refund override queue |
| A-PROMO | PENDING | 4 | promo CRUD |
| A-AREAS | PENDING | 4 | service areas CRUD |
| A-DISPUTE | PENDING | 4 | dispute resolution |

---

## Phase 6 — Launch gate (full suite)

| Test | Status | Notes |
|---|---|---|
| LG-double-accept | PENDING | concurrent double-accept |
| LG-webhook-same-window | PENDING | concurrent webhook |
| LG-webhook-vs-sweep | PENDING | both orderings |
| LG-cross-mode-overlap | PENDING | direct + broadcast overlap |
| LG-rebroadcast-idempotent | PENDING | duplicate rebroadcast |
| LG-refund-no-double | PENDING | refund retry safety |
| LG-manual-reassign | PENDING | admin reassign E2E |

See DISPATCH_FLOW.md §Test evidence (v2 launch gate).

---

## How to update (workflow)

1. Pick task from track file → set status to **IN_PROGRESS** when you start.
2. Implement → run acceptance from track file + relevant tests.
3. Set **COMPLETED** (or **SKIPPED** with reason) in the same PR/commit.
4. Re-check **Phase dashboard** — flip phase to IN_PROGRESS/COMPLETED as appropriate.
5. Run `pytest tests/ -q` and note count in the header line above.
