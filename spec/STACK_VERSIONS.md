# Stack Versions & Compatibility Matrix
# Puja Booking Platform — Backend

This document is the **single source of truth** for version decisions.
Every choice is justified. Cursor reads this before suggesting upgrades.

---

## Runtime

| Component | Pinned version | Min | Reason |
|---|---|---|---|
| **Python** | **3.12.x** | 3.12 | LTS until 2028. 3.13 works but skipping during initial build. 3.14 skipped until SQLAlchemy 2.1 ships. |
| **PostgreSQL** | **16.x** (local laptop install) | 16 | `btree_gist` + `postgis` + `pgcrypto` required. All three ship with PG16 via postgresql-16-contrib / postgis package. |

---

## Backend API layer

| Package | Pinned | Why this version |
|---|---|---|
| `fastapi[standard]` | **0.139.0** | Latest stable. Dropped Pydantic v1. `[standard]` bundles uvicorn, email-validator, python-multipart. |
| `pydantic` | **2.11.5** | Required by FastAPI 0.115+. Pydantic v1 is EOL. All models use v2 syntax (`model_config`, not `class Config`). |
| `pydantic-settings` | **2.9.1** | Reads `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY` etc. from env / `.env` file. |
| `uvicorn[standard]` | **0.34.0** | ASGI server. `[standard]` adds `uvloop` (2x speed) + `httptools` (faster HTTP parsing). |
| `orjson` | **3.10.18** | FastAPI auto-detects it and uses it instead of stdlib `json`. ~3x faster serialisation. |

---

## Database layer

| Package | Pinned | Why this version |
|---|---|---|
| `sqlalchemy` | **2.0.44** | Latest 2.0.x. 2.1 is in alpha — skip. Use 2.0 API throughout (`select()`, `Session`, mapped columns). Do NOT use legacy `Query` API. |
| `alembic` | **1.16.1** | Latest. Compatible with SQLAlchemy 2.0.x. |
| `psycopg[binary,pool]` | **3.2.13** | **psycopg3**, NOT psycopg2. Pin matches `pyproject.toml`. Async-native, PgBouncer transaction-mode compatible. |

> **Why psycopg3 not psycopg2?**
> psycopg2 is synchronous-only and has no native async support. The app uses
> `async def` everywhere for FastAPI. psycopg3's `AsyncConnection` integrates
> directly with SQLAlchemy's `AsyncEngine`. No thread executor hacks needed.

---

## Async job queue

| Package | Pinned | Why this version |
|---|---|---|
| `celery[redis]` | **5.6.3** | Latest stable. Native Pydantic v2 task args/returns. Fixed Redis disconnection bug (Kombu 5.4+). `[redis]` bundles redis-py. |
| `kombu` | **5.6.1** | Celery 5.6.x requires `kombu>=5.6.0`. Transport layer for the Redis broker. |
| `redis` | **5.3.1** | redis-py 5.x. Use **>=5.3.1** with `pyjwt==2.10.1` (5.3.0 pins PyJWT &lt;2.10). Adds `GETDEL` (WS tickets) and `mget` (dispatch presence). |

---

## Auth & security

| Package | Pinned | Why |
|---|---|---|
| `pyjwt` | **2.10.1** | `python-jose` is effectively abandoned (last release 2021, no maintainer). PyJWT is the replacement — actively maintained, simpler API. |
| `bcrypt` | **4.3.0** | OTP + refresh-token hashing, used DIRECTLY (passlib dropped — unmaintained). Must be >=4.0 for Python 3.12. |
| `python-multipart` | **0.0.20** | FastAPI form parsing. Required for OTP verify endpoint. Already bundled by `fastapi[standard]` but pinned explicitly to prevent accidental downgrade. |

---

## HTTP client (outbound calls)

| Package | Pinned | Why |
|---|---|---|
| `httpx` | **0.28.1** | Async HTTP for Razorpay API, FCM, FAST2SMS, MSG91 (via `sms_router`). Same interface as requests but fully async. Used by FastAPI's `TestClient`. |

---

## Logging & observability

| Package | Pinned | Why |
|---|---|---|
| `structlog` | **25.4.0** | Structured (JSON) logs in production, human-readable in dev. FastAPI middleware wraps each request with a `request_id`. |

---

## Dev / test tools

| Package | Pinned | Why |
|---|---|---|
| `pytest` | **8.3.5** | — |
| `pytest-asyncio` | **0.25.3** | `asyncio_mode = "auto"` in `pyproject.toml` — no `@pytest.mark.asyncio` boilerplate. |
| `pytest-cov` | **6.1.0** | Coverage. |
| `anyio[trio]` | **4.9.0** | Backend for async tests. |
| `ruff` | **0.11.9** | Linter + formatter. Replaces flake8, isort, black in one tool. |
| `mypy` | **1.15.0** | With `pydantic.mypy` + `sqlalchemy.ext.mypy.plugin`. |

---

## Flutter (mobile apps)

**Implementation contract:** [`MOBILE_FLUTTER.md`](./MOBILE_FLUTTER.md) · Firebase IDs: [`MOBILE_FIREBASE.md`](./MOBILE_FIREBASE.md)

**Authority:** `mana_guruji_mobile/pubspec.lock` (packages), `mana_guruji_mobile/.fvm/fvm_config.json` (Flutter SDK).
Human tables below are derived from the machine block. Enforced by `mana_guruji_mobile/tool/check_stack_versions_sync.py`.

<!-- stack-check:
flutter_sdk: 3.44.8
packages:
  dio: 5.11.0
  flutter_riverpod: 2.6.1
  go_router: 14.8.1
  firebase_core: 3.15.2
  firebase_messaging: 15.2.10
  flutter_secure_storage: 9.2.4
  web_socket_channel: 3.0.3
  google_fonts: 6.3.3
  url_launcher: 6.3.2
-->

### Layer A — Runtimes (mobile + toolchain)

| Layer | Pinned | Min | Max tested | Notes |
|-------|--------|-----|------------|-------|
| Flutter SDK | **3.44.8** (`.fvm/fvm_config.json`) | 3.38.4 | 3.44.8 | `fvm use` optional |
| Dart | **3.12.2** (bundled) | 3.11 | 3.12 | `pubspec.yaml` still `^3.8.0` — STACK-UPGRADE |
| JDK (Android) | 17 target | 17 | 21 | Studio JBR 21 OK |
| Android minSdk | 24 | 24 | — | Flutter 3.44 default |
| Android compile/targetSdk | 36 | 36 | — | |
| Android Gradle Plugin | 9.0.1 | — | 9.0.1 | `settings.gradle.kts` |
| Gradle | 9.1.0 | — | 9.1.0 | |
| Kotlin | 2.3.20 | — | 2.3.20 | |
| iOS deployment | **13.0** (current) | 13 | — | STACK-UPGRADE: raise to 15 |

### Layer B — Flutter packages (lockfile authoritative)

| Package | pubspec constraint | Lockfile resolved |
|---------|-------------------|-------------------|
| `dio` | ^5.7.0 | **5.11.0** |
| `flutter_riverpod` | ^2.6.1 | **2.6.1** |
| `go_router` | ^14.6.1 | **14.8.1** |
| `firebase_core` | ^3.12.1 | **3.15.2** |
| `firebase_messaging` | ^15.2.4 | **15.2.10** |
| `flutter_secure_storage` | ^9.2.4 | **9.2.4** |
| `web_socket_channel` | ^3.0.1 | **3.0.3** |
| `google_fonts` | ^6.2.1 | **6.3.3** |
| `url_launcher` | ^6.3.1 | **6.3.2** |

### PLANNED (not in pubspec yet)

| Package | When |
|---------|------|
| `google_maps_flutter` | Phase B booking-detail maps slice |

`web_socket_channel`: native WebSocket only — **not** `socket_io_client`. Server is FastAPI native WS + `POST /v1/ws-tickets`.

### Layer C — Cross-stack integration

| Integration | Client | Server | Forbidden |
|-------------|--------|--------|-----------|
| REST | Dio + generated client | FastAPI OpenAPI | Hand-written DTOs; Socket.IO |
| Auth | `flutter_secure_storage` | PyJWT 2.10 | `python-jose`; token in URL |
| Push | `firebase_messaging` | `fcm_client.py` HTTP v1 | Legacy FCM server key |
| Realtime | `web_socket_channel` | FastAPI native WS | `socket_io_client` |
| Payments | Razorpay Flutter SDK | Webhooks | **PLANNED Phase 3** |

### Layer D — Production gates (mobile)

| Gate | Status |
|------|--------|
| OpenAPI drift | `python tool/check_openapi_sync.py` |
| Stack doc drift | `python tool/check_stack_versions_sync.py` |
| Release Android signing | Debug keystore — prod task |
| iOS Firebase + APNs | Not registered — `MOBILE_FIREBASE.md` |

### Known doc drift (STACK-UPGRADE — do not fix silently)

| Item | Documented | Reality |
|------|------------|---------|
| `pubspec.yaml` SDK | `^3.8.0` | lockfile needs `>=3.11.0` |
| iOS floor | 13 in project | Recommend 15 |
| Release signing | debug | Play Store blocker |

---

## Next.js admin panel (for reference)

| Component | Version | Notes |
|---|---|---|
| Node.js | **20 LTS** (20.18.x) | LTS until 2026-04; 22 LTS also fine. Do not use odd (non-LTS) majors. |
| Next.js | **15.1.x** | App Router. React 19 bundled. |
| React | **19.0.x** | Ships with Next 15. |
| TypeScript | **5.7.x** | strict mode on. |
| `@tanstack/react-query` | **5.62.x** | Admin API data fetching + caching. |
| `zod` | **3.24.x** | Form + API response validation (Pydantic-equivalent mindset). |
| `tailwindcss` | **3.4.x** | Styling. |

## Key compatibility rules (Cursor must respect these)

1. **Never suggest `psycopg2`** — the project uses `psycopg` (v3) exclusively.
2. **Never suggest `python-jose`** — use `pyjwt` instead.
3. **SQLAlchemy models use 2.0 `Mapped[]` syntax** — never legacy `Column()` at class level.
4. **All DB calls are `async`** — `AsyncSession`, `AsyncEngine`, `async with session.begin()`.
5. **Pydantic models use v2 syntax** — `model_config = ConfigDict(...)`, not inner `class Config`.
6. **Do not pin Starlette separately** — FastAPI pins the compatible version.
7. **Do not upgrade to SQLAlchemy 2.1** until it is marked stable on pypi.
8. **Mobile contract:** on any `API_CONTRACTS.md` change, re-export `spec/openapi.json`
   (`DEBUG=true` → `GET /openapi.json`) for Flutter codegen; run `mana_guruji_mobile/tool/check_openapi_sync.py`.
9. **Stack doc:** after `flutter pub get` or FVM change, run `mana_guruji_mobile/tool/check_stack_versions_sync.py`.

---

## Version update policy

- Run `pip list --outdated` monthly.
- Minor bumps (e.g., 2.0.44 → 2.0.45): apply after reading changelog.
- Major bumps (e.g., Celery 5 → 6): full regression run required.
- Security patches: apply within 48h regardless of freeze.
