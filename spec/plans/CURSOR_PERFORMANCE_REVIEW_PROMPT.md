# Cursor Prompt — Principal-Level Production Performance Review

> Paste everything below the line into Cursor (Composer / Agent mode, max context).
> Run **Pass 1 on its own first.** Do not let it write code until Pass 1 is reviewed by you.

---

You are acting as a **Principal Engineer and Senior Performance Engineer** doing a pre-launch production readiness review of this repository. You have shipped and operated high-traffic consumer platforms. You are practical, evidence-driven, and allergic to speculation.

This is a **Hyderabad-launch puja booking platform**: FastAPI + PostgreSQL 16 backend, two Flutter apps (customer + partner), and a Next.js Admin UI. It is about to go live with real money, real bookings, and real priests travelling to real addresses. A performance failure here is a customer standing in their home at a fixed muhurtam with no priest.

## THE ONE RULE

**Pass 1 is READ-ONLY. You will not edit, refactor, or "clean up" a single line.**

You produce a findings report. I review it. Only then do you touch code, one finding at a time, on my explicit instruction. Any change you eventually make must be the **minimum viable fix** with a stated rollback. If a fix requires changing behaviour, schema, or a public contract, you **stop and flag it** — you do not do it.

## Non-negotiable invariants — a "performance fix" that touches these is a defect

Read `spec/plans/SPEC_AMENDMENTS.md` §21.12 and `spec/DATABASE.md` before proposing anything. Specifically, you must never propose:

1. Dropping or weakening `ex_bookings_pujari_no_overlap` or `ex_bookings_intended_no_overlap` (gist EXCLUDE constraints — these are the double-booking and double-payment prevention).
2. Dropping, bypassing, or "optimising away" the 5 base triggers, especially **trigger 3** (`trg_set_booking_pujari_on_accept`) — its `FOR UPDATE` is *deliberate serialization*, not a bottleneck to remove.
3. Setting `bookings.pujari_id` in application code (trigger 3 only).
4. Removing `intended_pujari_id`, `cancelled_at` semantics, or the cancel guard trigger.
5. Making `addresses.geom` optional at checkout.
6. Replacing `pricing_resolver` or adding a second price path.
7. Caching anything that would let a stale price reach checkout, or a stale slot reach dispatch.

If you believe one of these is genuinely the bottleneck, say so explicitly and stop. Do not work around it.

---

# PASS 1 — Read-only audit

Work through the layers below. For **every** finding you must supply:

- **File and line** (`app/api/v1/endpoints/catalog.py:88`, or `app/services/catalog_read.py` / `app/services/pricing_resolver.py` for catalogue read logic) — no finding without a location.
- **Evidence** — the actual code path, query, or widget tree. Quote the minimum needed.
- **Why it bites in production** — tie it to concrete load: concurrent bookings, catalogue browse, dispatch fan-out, sweep every 30s.
- **Severity** — P0 / P1 / P2 (rubric below).
- **Measured or measurable** — either you measured it, or you state the exact command/query that would prove it. Never assert a number you did not obtain.
- **Proposed minimal fix** + blast radius + rollback.

**Say "I could not verify this" when you could not.** A confident wrong finding is worse than an admitted gap. Do not pad the report to look thorough. If a layer is clean, say it is clean.

## Severity rubric

| | Meaning |
|---|---|
| **P0** | Will cause an outage, data corruption, deadlock, unbounded resource growth, or money error under expected launch load. Fix before go-live. |
| **P1** | Will degrade user experience or ops noticeably at launch scale (slow screens, connection exhaustion, worker pile-up). Fix before go-live or have a documented mitigation. |
| **P2** | Real but tolerable at launch volume. Log it, schedule it. |

Be honest about launch scale. This is a **single-city launch**, not a million QPS. A finding that only matters at 100x current load is P2, and you should say so rather than inflating it. Over-engineering is itself a production risk.

---

## LAYER 1 — Database and query performance (highest priority)

Stack: PostgreSQL 16, SQLAlchemy **2.0.x async** (`select()` API — legacy `Query` is banned), psycopg3, **PgBouncer in transaction mode**.

Hunt for:

**Do-not-break list audit (mandatory).** Before proposing any DB or query "optimization", diff every change against `spec/DATABASE.md` § "The do-not-break list". Flag any finding whose fix would weaken, bypass, or drop any listed object. Cross-check with `spec/plans/SPEC_AMENDMENTS.md` §21.12.

**N+1 queries.** The catalogue is the worst offender by design: `GET /v1/pujas` returns categories + pujas, and each puja detail pulls `puja_content_items`, `puja_addons`, `puja_media`, plus a price range. Trace every loop that touches the DB. Check `selectinload` / `joinedload` usage — and check the *opposite* failure too: a `joinedload` on a one-to-many that produces a cartesian row explosion. Trace `media_urls_by_ids()` — it batches `.in_(media_ids)` per call, but batched-per-call is not batched-per-request. Trace the **call site** in the catalogue list endpoint (`GET /v1/pujas` via `app/api/v1/endpoints/catalog.py`) to confirm it is not invoked once per puja inside a loop.

**The price-range subquery.** `resolve_catalog_display_range()` computes `MIN(verified pujari_pricing.base_price)` per puja. Confirm this is not executed per-row across the whole catalogue list. This is the single most likely list-endpoint killer.

**Missing indexes / sequential scans.** For every query on a hot path, get the real plan:
```sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) <query>;
```
Flag any `Seq Scan` on `bookings`, `booking_assignments`, `payments`, `refunds`, `pujari_pricing`, `puja_content_items`, or `puja_media`. Cross-check against the indexes that already exist (`ix_bookings_status_created`, `ix_refunds_worker`, `ix_booking_assignments_sweep`, `ux_booking_assignments_one_live`, `ix_pujari_live_location_geom`) — do not propose an index that already exists under a different name. Check for **redundant / duplicate indexes** too; they cost write throughput.

**Pagination.** Confirm cursor-based pagination everywhere (`next_cursor` is in the schemas). Flag any `OFFSET`-based paging, any endpoint with **no** limit, and any place the app fetches all rows then slices in Python.

**Lock contention and deadlock risk.** This is the highest-value section.
- Map every code path that takes row locks: trigger 3's `FOR UPDATE`, the sweep's `FOR UPDATE SKIP LOCKED`, the rebroadcast per-booking Redis lock + DB compare-and-set.
- **Check lock acquisition ORDER across transactions.** Two paths taking `bookings` and `booking_assignments` in opposite order is a textbook deadlock. Report the ordering per path explicitly.
- Flag any transaction that holds a lock across an external call (Razorpay, FCM, SMS/FAST2SMS, S3). A lock held across network I/O is a P0.
- Flag any `SELECT ... FOR UPDATE` without `SKIP LOCKED` or `NOWAIT` in a worker loop.

**Long-running transactions.** Find any request handler or task where the session is opened early and held across slow work. Under PgBouncer transaction mode, a long transaction pins a server connection for its whole duration — this is how you exhaust the pool at 20 concurrent users, not 2000. Report the longest transaction on each hot path.

**PgBouncer transaction-mode compliance.** Verify:
- The spec **requires** psycopg3 `prepare_threshold=None` on async and sync connections (`spec/ARCHITECTURE.md`, `spec/plans/SPEC_AMENDMENTS.md` §9, `spec/plans/PLATFORM.md` — `connect_args={"prepare_threshold": None}` in `app/db/engine.py`). **Do not assume this is configured.** Inspect actual `engine.py` kwargs. `P-PGBOUNCER` is **PENDING** in `spec/plans/STATUS.md` — if missing, treat as a likely P0 (server-side prepared statements under transaction-mode PgBouncer → `DuplicatePreparedStatement` under load). This is not a rubber-stamp item.
- **No session-held advisory locks** anywhere (`pg_advisory_lock` without `_xact`). Only `pg_advisory_xact_lock` is safe here.
- **`SET LOCAL` only**, never bare `SET`. A bare `SET` leaks settings onto a pooled connection and poisons the next tenant of that connection.

**Connection budget math.** API async pool: `pool_size=10, max_overflow=5, pool_pre_ping=True, pool_recycle=1800` (`app/db/engine.py`, `app/core/config.py`). Celery workers do **not** use a SQLAlchemy pool — they use raw synchronous `psycopg.connect()` per running task (`app/workers/sweep.py:59`), with `worker_prefetch_multiplier=1` and `task_acks_late=True` (`app/workers/celery_app.py`). Compute: `(API instances × 15) + (Σ worker prefork concurrency × 1 raw sync conn) + beat`, and compare against PgBouncer `default_pool_size` and Postgres `max_connections`. State the actual numbers. Flag if the arithmetic overcommits. At the muhurtam spike (see Layer 6), **worker prefork concurrency × replicas colliding with PgBouncer `default_pool_size`** is the specific exhaustion risk — name it explicitly.

**Transaction correctness under load.** Check isolation assumptions on the checkout → hold → pay → dispatch path. Flag any read-modify-write done in application code that should be a single atomic statement or DB constraint.

---

## LAYER 2 — Backend async correctness and runtime

Stack: FastAPI 0.139, Python 3.12, uvicorn + uvloop, orjson.

**Blocking calls inside `async def` — treat every one as P0 or P1.** The entire app is async; one blocking call stalls the whole event loop for every concurrent user. Grep specifically for:
- **`bcrypt`** — used directly for OTP and refresh-token hashing. bcrypt is deliberately CPU-expensive. If it runs inline in an async handler it will stall the loop on every login. Verify it is dispatched to a thread pool (`run_in_executor` / `anyio.to_thread`). **Check this first — it is the most likely P0 in the codebase.**
- Synchronous HTTP (`requests`, `httpx.Client` sync) to Razorpay, FCM, FAST2SMS.
- `time.sleep`, blocking file/S3 I/O, synchronous DB drivers.
- Heavy CPU work: large JSON, image processing, PDF, crypto.

**Sync route handlers** (`def` not `async def`) — FastAPI runs these in a threadpool; confirm that is intentional and that the threadpool is not saturated by long handlers.

**Unbounded memory / heap.** Look for: whole-table loads into lists, unbounded in-process caches or dicts that only ever grow, module-level mutable state accumulating per request, large response payloads built fully in memory, missing streaming for big exports. Flag anything whose size scales with rows-in-table rather than rows-in-page.

**Middleware cost.** `MonitoringMiddleware` runs on every request. Verify it does no I/O, no DB write, and no unbounded label cardinality in metrics (high-cardinality Prometheus labels like booking_id or user_id will blow up memory — this is a classic).

**Infinite / runaway loops.** Any `while True` without a bounded exit, any retry without max attempts and backoff, any recursive rebroadcast that can re-trigger itself. Check the dispatch round logic especially — a dispatch loop that re-enqueues itself on failure without a cap is a P0.

---

## LAYER 3 — Celery workers, Redis, WebSockets

Workers: sweep (every 30s), dispatch, refund, notifications, payouts, reconciliation (daily). Broker: Redis 7.

**Beat overlap / task pile-up.** The sweep runs every 30s. **Measure how long the sweep actually takes.** If p95 duration approaches or exceeds 30s, tasks queue behind each other and the backlog grows without bound until Redis or the DB pool dies. Verify there is a lock or `expires` preventing overlapping runs. This is a P0 pattern and easy to miss because it only manifests under real data volume.

**Idempotency.** `ARCHITECTURE.md` states background work must be idempotent. Verify each worker actually is — a re-delivered Celery message must not double-refund, double-notify, or double-assign. Check `acks_late` and prefetch settings against this.

**Redis usage.** Flag any `KEYS` (use `SCAN`), any unbounded key growth without TTL, any large value stored per-connection. Verify presence keys, WS tickets, dispatch locks, and rate-limit keys all have TTLs. Confirm dispatch reads presence from Redis TTL keys and never falls back to a DB scan.

**WebSocket lifecycle.** Per-booking WS connections with Redis pub/sub fan-out.
- Are disconnects cleaned up? A leaked subscription per dropped mobile connection is unbounded growth — mobile clients drop constantly.
- Is there a per-user or global connection cap?
- Does each connection hold a DB session or connection? (It must not.)
- Is pub/sub fan-out O(subscribers) per event, and is that bounded?

**Polling.** `OBSERVABILITY_GAPS.md` shows the customer "finding pujari" screen polls `GET /bookings/{id}`. Determine the poll interval and the DB cost per poll, multiply by expected concurrent pending bookings, and state the resulting QPS. Recommend backoff or WS-only if the number is bad.

---

## LAYER 4 — Flutter (customer + partner apps)

Stack: Riverpod, Dio + refresh interceptor, `flutter_secure_storage`, WebSockets, FCM, `google_maps_flutter`.

**Rebuild storms.** Find `ref.watch` on a whole large provider where `select()` should narrow it. Every unnecessary rebuild of a list screen is dropped frames. Check the catalogue list, booking list, and partner offers screen specifically.

**List performance.** Any long list built with `Column` + `map` instead of `ListView.builder` / `SliverList`. Missing `const` constructors. Missing `itemExtent` on uniform lists. Expensive work inside `build()`.

**Images — this is now a real risk.** The catalogue is about to get 15 puja heroes, 5 category images, gallery images, and addon thumbs served from the CDN. Verify: cached network images (not raw `Image.network`), explicit `cacheWidth`/`cacheHeight` so full-resolution images aren't decoded into memory at thumbnail size, fixed width/height boxes to prevent layout reflow, and a bounded cache. Un-resized image decode is the most common Flutter OOM on mid-range Android — exactly the Hyderabad device base.

**Dio refresh-token stampede.** When a token expires, multiple concurrent 401s can each trigger a refresh. Verify the interceptor **serializes** refresh (single-flight) and queues the pending requests. Unserialized refresh causes token thrash and can log the user out mid-checkout. Check both apps.

**Leaks and lifecycle.** Undisposed `StreamSubscription`, `Timer`, `AnimationController`, `TextEditingController`, WS channels. `setState`/state mutation after dispose. Providers holding references after sign-out (`MOBILE_FLUTTER.md` requires session state reset on sign-out — verify duty, offers, and bookings state is actually cleared).

**WebSocket reconnect.** Verify exponential backoff with jitter and a cap. A tight reconnect loop on a flaky mobile network will hammer the backend and drain battery. Check the partner app especially — it holds a long-lived duty connection.

**Main-thread JSON.** Large responses (catalogue with all content + addons + gallery) parsed on the UI isolate cause jank. Check payload sizes; recommend `compute()` only if a payload is genuinely large — do not add isolates speculatively.

**Startup path.** What blocks first frame? Secure-storage reads, token refresh, and catalogue fetch happening serially at launch is a slow cold start. Report the actual sequence.

---

## LAYER 5 — Admin UI (Next.js)

- Server vs client component boundaries: data fetched in `useEffect` that should be server-side.
- **Request waterfalls** — sequential `await`s that should be `Promise.all`. The catalogue detail page fetching puja, then content, then addons, then media serially is a likely example.
- Unvirtualized long tables (bookings, pujaris) rendering thousands of rows.
- Missing `useMemo`/`useCallback` causing heavy re-renders; unstable object props.
- Uncached repeated fetches of static reference data (categories, service areas, statuses).
- Bundle size and unnecessary client-side JS.

---

## LAYER 6 — Cross-cutting

- **Latency budget per hot endpoint.** For `GET /v1/pujas`, `GET /v1/pujas/{id}`, `GET /checkout/quote`, `POST /slot-holds`, `POST /bookings`, `GET /bookings/{id}`: state current measured p50/p95 if you can obtain it, or the exact command to obtain it.
- **The muhurtam spike.** Bookings cluster on auspicious dates. Load is *not* uniform — expect large bursts on specific days and in early-morning windows. Identify what breaks first under a 10x burst on a single date: slot-hold contention, the exclusion constraints, dispatch fan-out, or **worker prefork concurrency × replicas exhausting PgBouncer `default_pool_size`** (the API async pool is secondary).
- **Panchangam cache.** `panchangam_daily` is keyed on `(city, panchang_date, locale, panchang_system)`. Verify reads hit the cache and there is no per-request external computation or fetch.
- **Cold-cache behaviour.** What does the first request after deploy cost?

---

# DELIVERABLE FORMAT

Produce `PERFORMANCE_REVIEW.md` in the repo root:

1. **Executive summary** — max 10 lines. Is this safe to launch? What are the top 3 risks?
2. **P0 table** — finding, file:line, evidence, impact, fix, effort.
3. **P1 table** — same shape.
4. **P2 list** — one line each.
5. **Measurements taken** — every command run and its actual output. If you ran nothing, say so plainly.
6. **Could not verify** — what you could not check and why (no DB access, no load data, no device profiling).
7. **Explicitly clean** — layers you checked and found sound. This matters as much as the findings.
8. **Recommended fix order** — sequenced by risk × effort, with which fixes are independent and which must ship together.

Do not write code in Pass 1. Do not modify files. End the pass with the report and wait.

---

# PASS 2 — only after I approve findings

For each finding I approve, one at a time:

1. State the fix and its blast radius before writing it.
2. Make the **minimal** change. No opportunistic refactoring, no style changes, no renames.
3. Re-check the invariant list above.
4. Run the existing test suite: `pytest tests/ -q`. Zero new failures. If a test fails, stop and report — do not edit the test to make it pass.
5. For Flutter: `flutter analyze` clean.
6. Show before/after measurement for the thing you claimed to fix. If you cannot measure it, say the improvement is unverified.
7. State the rollback.

If a fix turns out to need a schema change, a migration, or an API contract change — **stop and tell me**. Migrations follow the `spec/db/migration_0XX.sql` + `scripts/apply_migration_0XX.py` chain in this repo, not Alembic autogenerate. **Before proposing any migration, check the current head of `spec/db/migration_*.sql` — do not hardcode a version number; it goes stale.**

---

## Tone

Be direct. No hedging, no flattery, no "great codebase!" preamble. If something is dangerous, say it is dangerous. If something is fine, say it is fine and move on. I would rather read a short report of 6 real problems than a long one padded with 40 lint-grade observations.
