# Production-Readiness Review — Fixes Applied

Every P0 and P1 from the review, with verification status.

## P0 — blocked local run (all fixed + tested)

| # | Issue | Fix | Verified |
|---|---|---|---|
| 1 | `sweep.py` imported **psycopg2** (not even in deps) | Rewrote with **psycopg3**, added `_normalize_db_url()` to strip `+psycopg` driver suffix | ✅ Ran all 5 steps against `mana_guruji` DB |
| 2 | `celery -A app.workers.celery_app` → module didn't exist | Created **`app/workers/celery_app.py`** (central app, beat schedule, queue routing) | ✅ Imports clean; `sweep_task` registers under correct name |
| 3 | Sweep missing v3 steps (abandon, presence, lock) | Added step 2 (abandon payment_pending + `cancelled_at` + release holds), step 5 (presence sync), Redis `sweep_lock` NX EX 25 | ✅ Abandoned booking flips + `cancelled_at` set, verified |
| 4 | DB name mismatch | `.env.example` + CURSOR_SETUP now use **`Mana_Guruji`** | ✅ DB built + seeded under that name |

## Extra bug found during testing (not in review)

- Sweep step 2 used `held_by_user_id`; real `slot_holds` column is **`user_id`**.
  Caught by running against the actual schema. Fixed.

## P1 — before staging (all fixed)

| # | Issue | Fix |
|---|---|---|
| 5 | Flutter `socket_io_client` incompatible with native WS server | STACK_VERSIONS + project.mdc now mandate **`web_socket_channel`** |
| 6 | No Node/Next.js pins | Added Node 20 LTS, Next 15.1, React 19, TS 5.7, TanStack Query, Zod |
| 7 | `build-backend = setuptools.backends.legacy:build` (invalid) | Corrected to **`setuptools.build_meta`** |
| 8 | passlib unmaintained | Dropped passlib; **bcrypt used directly** in `app/core/security.py` (SHA-256 pre-hash for 72-byte safety) |
| — | CURSOR_SETUP Windows gaps | Added PowerShell uv install + Redis via WSL2/Memurai/Docker |
| — | project.mdc gaps | Added worker psycopg3-sync rule, WS lib rule, Next.js pins |

## New files
- `app/workers/celery_app.py` — central Celery app
- `app/core/security.py` — bcrypt-direct + PyJWT + Razorpay signature verify

## Verified against live `Mana_Guruji` (PostgreSQL 16)
- 5-file DB build: 0 errors, 13 status_types
- Sweep worker: holds released, payment_pending→abandoned+cancelled_at,
  offers→expired, stranded booking flagged, idempotent 2nd run, all via psycopg3
- Celery app imports; beat schedule + 4 queues load; task name == import path
- Security: OTP hash/verify, JWT app_context round-trip, no passlib/jose imported

## Still open (P2 — as the review states, before production, not blocking build)
- Scaffold Flutter (customer + pujari flavors) with `web_socket_channel`
- Scaffold Next.js admin (Node 20 LTS)
- Run all 16 v3 launch-gate tests against Mana_Guruji
- Commercial agreements: Razorpay, Maps, FCM, MSG91 DLT, S3 KYC residency
