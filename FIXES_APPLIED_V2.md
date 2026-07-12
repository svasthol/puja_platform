# FIXES_APPLIED_V2 — Mana Guruji backend build

This document records every change made on top of the ~15%-scaffolded upload:
the confirmed bug fixes, the ~85% of the backend that was built out, and the
live verification performed against a real PostgreSQL 16 + PostGIS instance.

> Honesty note: this is a thorough, spec-faithful implementation with the
> identified bugs fixed and the critical flows proven against a live DB. It is
> **not** a substitute for a full staging soak, load test, and security review.
> "Bug-free" is not a claim anyone can make about a payments/dispatch system;
> what is claimed here is specific and testable, and the tests are included.

---

## 1. Confirmed bugs fixed

### P0 — Exception handlers never fired (all 4xx became 500)
`app/core/exceptions.py` **rewritten**. The original registered handlers on raw
`psycopg.errors.*` classes. Under async SQLAlchemy, DB errors arrive wrapped as
`sqlalchemy.exc.DBAPIError` (e.g. `IntegrityError`, `ProgrammingError`), which is
**not** a subclass of the psycopg types — so no handler matched and every
constraint/trigger violation returned HTTP 500.
Fix: a single handler on `DBAPIError` unwraps `.orig` and dispatches on the
psycopg error via `map_db_error()`, keyed by SQLSTATE + `diag.constraint_name` +
trigger message. Raw-psycopg handlers remain registered as a defensive fallback.
**Proven live:** `ux_slot_holds_active` (IntegrityError) → 409; accept-on-cancelled
booking (ProgrammingError from trigger P0001) → 410. Both were 500 before.

### P0 — Missing dispatch worker (`NotRegistered` on rebroadcast)
`sweep.py` enqueued `app.workers.dispatch.rebroadcast_booking`, which did not
exist. Built `app/workers/dispatch.py` with `broadcast_booking` /
`rebroadcast_booking`, layered idempotency (Redis lock → DB round compare-and-set
→ `ux_booking_assignments_one_live`), radius rounds (3/6/10/15 km), Redis-presence
eligibility, and exhaustion → `failed_no_pujari` + `cancelled_at` + refund row.

### Bug — sweep step 2 released the wrong holds
`abandon_stale_payment_pending` released **all** of a user's active holds
(`WHERE user_id IN ...`). Rewritten to release only the hold linked to each
abandoned booking via `bookings.hold_id`, and to write a `booking_status_history`
row. **Proven live:** a user with two active holds keeps the unrelated one.

### Hardening — bcrypt NUL truncation
`security.py` `_prehash` fed a raw SHA-256 digest to bcrypt; ~11% of digests
contain 0x00, which some bcrypt backends truncate at. Now base64-encodes the
digest (44 bytes, NUL-free, < 72). Added `create_refresh_token`.

### Doc/config drift
- `.env.example`: `puja_platform` → `Mana_Guruji`.
- `spec/STACK_VERSIONS.md`: removed the stale `passlib[bcrypt]` row (dropped in pyproject).
- `sweep.py`: switched from `logging` to structlog (project.mdc rule).

---

## 2. Backend built out (was absent in the upload)

- **Core:** `logging.py` (structlog + RequestIDMiddleware), `redis_client.py`
  (async, GETDEL), `dependencies.py` (`Principal`, JWT auth, `app_context`
  enforcement → 403, single-use WS tickets), `db/engine.py` `get_db_txn`.
- **Models:** `app/models/*` — all 31 ORM tables (SQLAlchemy 2.0 `Mapped`).
- **Schemas:** `app/schemas/*` — Pydantic v2.
- **Services:** status lookup (by `(domain,code)`), Razorpay client (async order
  inside txn w/ tight timeout; sync refund for the worker), booking checkout
  (one-txn, insert-before-Razorpay so duplicate-submit fires early), webhook
  (idempotent, SAVEPOINT around the paid_at flip, auto-refund on overlap/late),
  cancellation (state-gated, policy %, capped at `amount_due_online`), offers
  (single-UPDATE accept lets trigger 3 do the rest; reject fast-path rebroadcast).
- **Endpoints (23):** auth, catalog, slot-holds, checkout quote, bookings,
  cancel, dispatch-choice, offers accept/reject/list, pujari heartbeat, service
  lifecycle (start / confirm-balance / complete), admin advance-amount, Razorpay
  webhook, WS tickets + booking socket. `main.py` wires middleware, CORS,
  router, and a DB+Redis readiness `/health` (503 when degraded).
- **Workers:** dispatch, refund (backoff, idempotency=refunds.id, crash requeue,
  8-attempt cap), notifications (FCM/SMS stubs, logged), sweep (5 steps), celery
  includes uncommented + refund beat.

---

## 3. Verified against live PostgreSQL 16 + PostGIS 3.4

- DB built from `spec/db/*.sql` with **zero errors**: 48 tables, 13 status_types,
  2 exclusion constraints, 11 partial unique indexes, all triggers.
- All 19 app modules + full FastAPI app import cleanly; 23 OpenAPI paths.
- **`tests/` launch-gate suite: 4 passed (twice, rerunnable):**
  exception mapping → 409/410, double-accept race (first wins, second raises),
  sweep step-2 (only linked hold released).

Run the tests yourself:
```bash
createdb Mana_Guruji
psql -d Mana_Guruji -f spec/db/schema.sql -f spec/db/triggers.sql \
     -f spec/db/seed.sql -f spec/db/migration_002.sql -f spec/db/migration_003.sql
export DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:5433/Mana_Guruji
export SECRET_KEY=change-me-at-least-32-characters-long REDIS_URL=redis://localhost:6379/0
pytest -q
```

---

## 4. Known limitations (deliberately not hidden)

- **Promo redemption** is scaffolded but the discount is applied as 0% in
  `booking_service.compute_amounts` (placeholder). Wire promo validation +
  `promo_redemptions` insert before enabling promo codes in production.
- **FCM / MSG91** are stubbed in the notification worker (logged, not sent).
- **Redis DB separation** (`REDIS_DB_CELERY` / `REDIS_DB_PRESENCE`) is single-DB
  by design for phase 1; split before multi-tenant scale if needed.
- These integration tests require a live PG16; they intentionally do not mock the
  DB, because the DB *is* the invariant layer. Add API-level tests with an ASGI
  test client and a Redis fake as a follow-up.
