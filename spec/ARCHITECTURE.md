# Architecture — Puja Booking Platform (v3.2, go-live)

Two-sided marketplace (Uber/Rapido model): customers book pujas, pujaris accept
and perform them. One shared backend, two mobile apps, one admin panel. Single
city at launch; multi-city is a data change (`service_areas`), not a code change.

v2 closes the gaps found in architecture review: unpaid-booking lifecycle,
refund state machine, dispatch rounds with geo radius, Redis-TTL presence,
WebSocket ticket auth, and hard multi-instance gates. **v3 adds dual payment
models** (`full_online` | `advance_balance`). **v3.1 adds idempotent checkout**
(`bookings.razorpay_order_id` + SAVEPOINT duplicate handling on
`POST /v1/bookings`). DISPATCH_FLOW.md is the behavioural source of truth;
DATABASE.md carries migrations 002, 003, and 004 DDL.

## Stack (final)

| Layer | Choice | Notes |
|---|---|---|
| Customer app | Flutter | Same codebase as pujari app, separate build flavor |
| Pujari app | Flutter | Build flavor of the same codebase |
| Admin panel | Next.js + TypeScript | Internal only |
| Backend API | FastAPI | Python 3.12 |
| ORM / migrations | SQLAlchemy 2.0 + Alembic | See DATABASE.md — the SQL files are the source of truth, not the ORM |
| Database | PostgreSQL 16 | Extensions REQUIRED: `pgcrypto`, `btree_gist`, `postgis` (dispatch radius queries use `ST_DWithin`; see migration 002) |
| Connection pooling | PgBouncer (transaction mode) | See "Connection policy" below — not optional past 1 API instance |
| Cache / rate limiting / presence | Redis 7 (AOF persistence + 1 replica) | OTP rate limits, pujari presence TTL keys, WS tickets, dispatch locks, WS pub/sub |
| Async jobs | Celery + Celery Beat, **broker = Redis** (deliberate single-dependency choice, see below) | Workers: sweep (30s), dispatch, refund, notifications, payouts, reconciliation (daily) |
| Realtime | WebSockets (FastAPI native) | ALL fan-out via Redis pub/sub channels from day one — see rule 6 |
| Push | Firebase Cloud Messaging | Best-effort only; `GET /v1/offers` polling is the delivery safety net — see DISPATCH_FLOW.md |
| SMS / OTP | MSG91 (or Exotel) | OTPs stored hashed (`otp_verifications.otp_hash`), never raw; SMS is also the push-failure fallback for direct offers |
| Payments | Razorpay | Orders + webhooks + refunds API; webhook signature verification is a MUST; `payments.idempotency_key` dedupes retries |
| Storage | S3-compatible (R2/MinIO) | KYC docs in a PRIVATE bucket, SSE enabled, signed URLs only |
| Maps | Google Maps Platform | |
| Reverse proxy | Nginx or Caddy | TLS + WebSocket proxying |
| Monitoring | Prometheus + Grafana + Sentry | Alert on: `refunds.status='failed_permanent'`, dispatch exhaustion rate, webhook signature failures, **stuck `payment_pending` past hold+grace**, **stuck `confirmed` past scheduled_time+90min without start**, refunds pending high `attempt_count` (v3.2) |
| Secrets | AWS SSM Parameter Store / Doppler (env injection) | Never `.env` in repo. Razorpay keys + KYC bucket keys: rotation owner assigned, quarterly cadence |

## System layout

```
[Customer app]   [Pujari app]        [Admin panel]
      \              /                     |
       \            /                      |
        [Nginx] -> [FastAPI backend xN] ---- [Redis] (presence TTL, ws pub/sub,
         |               |        \            rate limits, dispatch locks,
         |               |         \           celery broker, ws tickets)
         |               |          [Celery workers + Beat]
         |               |            sweep(30s) / dispatch / refund /
         |               |            notifications / payouts / reconcile(daily)
         |          [PgBouncer]
         |               |
   [PostgreSQL 16 + PostGIS]   [S3 private bucket]   [Razorpay / FCM / MSG91 / Maps]
```

## Non-negotiable design rules

1. **Booking integrity lives in the database, not the app.** Row locks, exclusion
   constraints, and triggers enforce no-double-booking — including the v2
   paid-booking exclusion `ex_bookings_intended_no_overlap`, which makes it
   impossible for two PAID bookings to target the same pujari time window even
   if every app-layer guard fails. App code provides UX on top of those
   guarantees; it is never the only line of defense.
2. **`app_context` on every session.** Tokens issued by the customer app cannot
   call pujari-only endpoints even for dual-role users. Enforced in the auth
   dependency, driven by `auth_sessions.app_context`.
3. **Never store raw secrets.** OTPs and refresh tokens are hashed
   (`otp_hash`, `refresh_token_hash UNIQUE`). KYC document URLs point to a
   private bucket; API returns short-lived signed URLs. WS auth uses
   single-use Redis tickets — bearer tokens NEVER appear in URLs or logs.
4. **Money math is trigger-computed, money movement is a state machine.**
   `payment_splits.net_pujari_amount` is written by a DB trigger on the
   **platform-captured amount only** (`amount_due_online`). Two payment
   models coexist: `full_online` (100% via Razorpay) and `advance_balance`
   (configurable advance via Razorpay — `platform_settings.advance_booking_amount`,
   admin-tunable without redeploy — + rest collected directly by pujari, never
   through the platform). Refunds are capped at `amount_due_online`. Every
   refund is a `refunds` row with retry state — Razorpay is NEVER called
   inline in a request handler.
5. **Every booking state change is recorded** in `booking_status_history`,
   including cancellation (which flips `status_id` AND sets `cancelled_at`
   atomically) — this is the audit trail for disputes and support.
6. **All WebSocket fan-out goes through Redis pub/sub channels
   (`booking:{id}`) from day one, even with a single API instance.** Any pod
   can then serve any socket; no sticky sessions. Running >1 API instance
   without this is a silent-outage class bug, not a degradation.
7. **Dispatch reads presence from Redis TTL keys, never from
   `pujaris.is_online`.** A crashed app goes offline by TTL lapse (90s);
   no stuck-online state is possible. The DB column is analytics-only.
8. **Background work is idempotent.** Sweep uses `FOR UPDATE SKIP LOCKED`;
   rebroadcast uses a per-booking Redis lock plus a DB compare-and-set on
   `booking_dispatch_state.round`. Duplicate task delivery is harmless by
   construction.

## Connection policy (PgBouncer + SQLAlchemy)

- PgBouncer in **transaction mode** in front of PostgreSQL.
- FastAPI: `pool_size=10, max_overflow=5, pool_pre_ping=True, pool_recycle=1800`.
- **psycopg3 prepared statements:** set `prepare_threshold=None` on async and sync
  connections when using PgBouncer transaction mode (avoids "prepared statement
  already exists" errors in staging/production).
- Celery workers: `pool_size=2` each.
- Budget: total client connections < 80% of `max_connections`.
- Constraint of transaction mode: no session state across transactions
  (no session-held advisory locks, `SET` only as `SET LOCAL`). All triggers
  and `FOR UPDATE` patterns in this design are transaction-scoped — compatible.

## Redis as single dependency — deliberate, with mitigations

Redis is broker + cache + presence + pub/sub. Accepted for launch because:
- AOF persistence + replica covers process loss.
- The sweep worker's independent stranded-booking scan (DISPATCH_FLOW.md)
  means lost dispatch tasks are re-detected within 30s of Redis recovery —
  the system self-heals from broker loss by design.
- Presence keys lapsing during an outage fails SAFE (pujaris appear offline,
  dispatch pauses) rather than dispatching to ghosts.
Revisit (dedicated broker) only if Redis becomes a measured bottleneck.

**API process:** `redis.asyncio` pool is created in FastAPI `lifespan` startup
(`init_redis()` + PING), closed on shutdown. Request-path commands use
`redis_execute()` — on stale connection (idle timeout, network blip, dead
asyncio transport) the pool is reset once and the command retried; persistent
failure maps to **503** (`RedisUnavailable`), not 500. Pool options:
`health_check_interval=30`, `socket_keepalive=True`, `retry_on_timeout=True`,
exponential backoff retries.

## Database roles

- App connects as `puja_app`: `SELECT/INSERT/UPDATE` on app tables only.
  **No `DELETE`** (audit rules forbid deletes — enforced at the grant level),
  no DDL, not superuser.
- Alembic migrations run as separate `puja_migrate` role (DDL owner).

## Payment product policy (v3.2)

- **`full_online`** is the default checkout option in client UI.
- **`advance_balance`** is opt-in. Offline balance is collected directly by the
  pujari — high disintermediation risk for repeat festival/annual bookings.
- **Commission base** = `amount_due_online` only (see DATABASE.md). Not a bug.

## Development plans

Implementation sequence and status: `spec/plans/MASTER.md`, `spec/plans/STATUS.md`.
Spec additions log: `spec/plans/SPEC_AMENDMENTS.md`.

## Open items (explicitly NOT done — do not assume otherwise)

- GST is a single `gst_amount` column; CGST/SGST breakout is a planned
  migration before invoicing goes live (single-state launch, so no IGST branch).
- Platform timezone is fixed to `Asia/Kolkata` for launch; all
  `scheduled_date + scheduled_time` arithmetic (refund 24h cutoff, start
  window) MUST use this zone explicitly, never server-default TZ. A
  `bookings.timezone` column is the planned multi-region migration.
- Encryption-at-rest for KYC files = infra config (private bucket + SSE),
  gate launch on it.
- Backup/DR: pick managed Postgres (PITR) or self-hosted `pg_dump` + WAL
  archiving once hosting is chosen.
- Partitioning `booking_status_history` / `chat_messages`: revisit past
  ~tens of millions of rows; premature now.
