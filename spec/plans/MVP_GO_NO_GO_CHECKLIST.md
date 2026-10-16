# Hyderabad Puja MVP — go / no-go checklist (production)

**Scope:** Ship **broadcast marketplace** with **`payment_mode=booking_fee`**, **TDS OFF**, **Phase 3 payouts ON HOLD** — per [`LAUNCH_POLICY.md`](./LAUNCH_POLICY.md), [`TDS_LAUNCH_STATUS.md`](./TDS_LAUNCH_STATUS.md) §0.L, [`project.mdc`](../../.cursor/rules/project.mdc).

**Authority:** Task status in [`STATUS.md`](./STATUS.md). This page is the **ops sign-off** for first prod cut (incl. OCI/Linux). It does **not** replace legal/CA sign-off or Phase 6 concurrent-test evidence in [`DISPATCH_FLOW.md`](../DISPATCH_FLOW.md).

**Decision rule:** **NO-GO** if any **P0** row fails. **P1** may ship only with a named owner + dated waiver in this file’s sign-off table.

---

## A. Product posture (must be true in prod `.env`)

| ID | Check | P | Pass? | Evidence |
|----|--------|---|-------|----------|
| A1 | `APP_ENV=production`, `DEBUG=false` (no `/docs`, no `otp_dev_only`) | P0 | ☐ | `app/main.py` disables OpenAPI when `DEBUG=false` |
| A2 | `FULL_ONLINE_ENABLED=false` — launch = **booking_fee** only (Razorpay = frozen fee; puja offline) | P0 | ☐ | `project.mdc` §Puja MVP launch |
| A3 | `TDS_ACCRUAL_ENABLED=false` | P0 | ☐ | [`TDS_RUNTIME_CONFIG.md`](./TDS_RUNTIME_CONFIG.md) |
| A4 | `TDS_ACCEPT_STUB_COLLECT=false` | P0 | ☐ | Staging-only fake collect |
| A5 | `PAN_ACCEPT_GATE_ENABLED=false` unless ops deliberately tightens | P1 | ☐ | Optional hard gate |
| A6 | `PUJARI_FY_PAN_GATE_ENABLED=false` at first prod cut (enable after staging S14 + `--strict`) | P1 | ☐ | [`TDS_STAGING_ROLLOUT.md`](./TDS_STAGING_ROLLOUT.md) |
| A7 | `PLATFORM_TIMEZONE=Asia/Kolkata` | P0 | ☐ | `app/core/config.py` |
| A8 | `ALLOWED_ORIGINS` includes prod admin UI + app origins only | P0 | ☐ | CORS |
| A9 | §0.C risk acceptance signed (L5) + CA memo owners named (L6) | P1 | ☐ | [`TDS_LAUNCH_STATUS.md`](./TDS_LAUNCH_STATUS.md) §0.L — **policy gate**, not code |

---

## B. OCI / Linux runtime (API host)

| ID | Check | P | Pass? | Evidence |
|----|--------|---|-------|----------|
| B1 | **Linux** VM/container (not Windows) for API + Celery | P0 | ☐ | [`CURSOR_SETUP.md`](../../CURSOR_SETUP.md) §Supported platforms |
| B2 | Python **3.12** (see `pyproject.toml` `requires-python`) | P0 | ☐ | |
| B3 | **PostgreSQL 16 + PostGIS 3** (`CREATE EXTENSION postgis`; `btree_gist`) | P0 | ☐ | [`DATABASE.md`](../DATABASE.md), dispatch `ST_*` in `pujaris.py` |
| B4 | **Redis** reachable; `REDIS_URL` set | P0 | ☐ | Presence, Celery, sweep locks (`APP_ENV:` prefix) |
| B5 | **HTTPS** LB → API; Razorpay + Setu callbacks are **public** URLs | P0 | ☐ | Webhooks |
| B6 | API: `uvicorn` (or gunicorn+uvicorn workers), **not** `--reload`; bind `0.0.0.0` behind LB | P0 | ☐ | |
| B7 | Celery **worker**: `-Q sweep,dispatch,refund,notifications` (no `--pool=solo`) | P0 | ☐ | `app/workers/celery_app.py` |
| B8 | Celery **beat** running (30s sweep + DV2 beats + refunds + panchangam + TDS intent tick) | P0 | ☐ | Same module `beat_schedule` |
| B9 | `GET /health` → DB + Redis OK; `sweep_age_seconds` sane | P0 | ☐ | `app/main.py`; migration **024** `worker_heartbeats` |
| B10 | **S3-compatible** storage (`S3_ENDPOINT_URL`, buckets) for KYC + catalog | P0 | ☐ | OCI Object Storage OK via S3 API |
| B11 | `FCM_SERVICE_ACCOUNT_PATH` on host (Firebase JSON); partner + customer flavors per [`MOBILE_FIREBASE.md`](../MOBILE_FIREBASE.md) | P1 | ☐ | Push is best-effort; poll is safety net |
| B12 | Panchangam engine **private** to VPC; `PANCHANGAM_VENDOR_URL` not public | P1 | ☐ | [`PANCHANGAM_OPS.md`](./PANCHANGAM_OPS.md) §Prod |
| B13 | Optional: `SENTRY_DSN`, `METRICS_ENABLED` | P2 | ☐ | Phase 7 not required for MVP |

**Not in repo:** Dockerfile/Terraform for OCI — provision manually or add later.

---

## C. Database — migration chain (fresh prod)

**Two tracks:** Alembic **001→011**, then SQL **012→034** via `scripts/` (no `migration_007.sql` / **008** — Phase 3 tax geom reserved; MVP does **not** need 007 for `booking_fee` launch per [`DATABASE.md`](../DATABASE.md)).

Run from `puja_platform/` with superuser `DATABASE_URL` unless noted.

| Step | Command / action | P | Pass? |
|------|------------------|---|-------|
| C1 | `alembic upgrade head` (001–011 incl. **009** admin auth) | P0 | ☐ |
| C2 | `python scripts/apply_migration_012.py` … **027** in order (**012–018, 019–024, 025–027**) | P0 | ☐ |
| C3 | `python scripts/apply_migrations_028_032.py` (applies **028–034** idempotent) | P0 | ☐ |
| C4 | `python scripts/bootstrap_puja_app_role.py` then `python scripts/apply_grants.py` | P0 | ☐ | **Before** relying on append-only TDS ledger / statutory REVOKEs (R12) |
| C5 | Point `DATABASE_URL` at **`puja_app`** for API/workers in prod | P0 | ☐ | After C4 |
| C6 | Seed **status_types** present (001 seed); no booking until seed gate satisfied | P0 | ☐ | [`DISPATCH_FLOW.md`](../DISPATCH_FLOW.md) §Seed-data contract |
| C7 | Hyderabad catalogue + service areas + RM: `bootstrap_catalog.py` / ops data per [`CATALOG_SYNC.md`](./CATALOG_SYNC.md) | P0 | ☐ | |
| C8 | `python scripts/bootstrap_admin.py` + `TOTP_ENC_KEYS` in env | P0 | ☐ | [`ADMIN.md`](./ADMIN.md) Sprint 4-0 |
| C9 | Migrations **015** + **016** applied (monitor tables) — included in C2 script list | P0 | ☐ | `STATUS.md` observability prereq |

**Every deploy:** re-run `python scripts/apply_grants.py` (idempotent).

---

## D. TDS / schema readiness (prod DB, TDS OFF)

| ID | Check | P | Pass? | Evidence |
|----|--------|---|-------|----------|
| D1 | `python scripts/check_tds_readiness.py` — report; **no unexpected NO** on 025–034 columns | P0 | ☐ | [`TDS_READINESS.md`](./TDS_READINESS.md) |
| D2 | On **clean prod** (no staging accrual pollution): `python scripts/check_tds_readiness.py --strict` exits 0 | P0 | ☐ | Strict = schema complete + **zero FY TDS drift** |
| D3 | Prod `.env` confirms A3–A4; worker may run TDS tick harmlessly with flag off | P1 | ☐ | Intents should not pile up if nothing enqueued |

`--strict` is **mandatory before** `TDS_ACCRUAL_ENABLED=true` or `PUJARI_FY_PAN_GATE_ENABLED=true`; at MVP OFF it still validates schema + reconciles **empty/zero** ledger.

---

## E. Integrations & secrets

| ID | Check | P | Pass? |
|----|--------|---|-------|
| E1 | `SECRET_KEY` ≥ 32 chars; not dev placeholder | P0 | ☐ |
| E2 | `DATABASE_URL` uses `postgresql+psycopg://` (driver normalized in config) | P0 | ☐ |
| E3 | Razorpay **live/test** keys + **`RAZORPAY_WEBHOOK_SECRET`** matches dashboard URL | P0 | ☐ |
| E4 | SMS: **DLT-approved** templates OR accepted pilot without SMS (no silent OTP failure) | P0 | ☐ | `project.mdc` DLT gate |
| E5 | Setu **prod** `KYC_SETU_*` + `KYC_REDIRECT_URL`; `KYC_SETU_PAN_PRODUCT_ID` for operative PAN in prod | P1 | ☐ | `pujari_compliance.py` 503 if prod PAN verify missing |
| E6 | `GOOGLE_MAPS_API_KEY` if checkout map used | P1 | ☐ |

---

## F. Smoke & lifecycle (post-deploy)

| ID | Check | P | Pass? |
|----|--------|---|-------|
| F1 | `python scripts/dev_api_smoke.py` against prod URL (or staging mirror) | P1 | ☐ |
| F2 | One **paid** broadcast booking: hold → book → webhook → dispatch → accept → confirm-balance → complete | P0 | ☐ | E2E runbook: `CURSOR_SETUP.md` Step 10 |
| F3 | `python scripts/verify_sweep_e2e.py` on staging with test UUIDs **or** prod-like env | P1 | ☐ | Sweep + migration 024 |
| F4 | Admin: login TOTP, KYC approve, booking search, reassign smoke | P1 | ☐ | [`ADMIN.md`](./ADMIN.md) exit gate (partial OK for MVP) |
| F5 | Partner app: register → KYC → verified → heartbeat → accept (device) | P0 | ☐ | `STATUS.md` §Mobile |
| F6 | Customer app: checkout + booking detail (device) | P0 | ☐ | |
| F7 | Phase **6** concurrent tests (`LG-*` in `STATUS.md`) green **or** waiver | P1 | ☐ | [`DISPATCH_FLOW.md`](../DISPATCH_FLOW.md) v2/v2 DV2 gates |

---

## G. Explicit NO-GO (do not ship)

- `TDS_ACCRUAL_ENABLED=true` or `TDS_ACCEPT_STUB_COLLECT=true` on prod without S14 + dated [`TDS_CODE_REVIEW.md`](./TDS_CODE_REVIEW.md) run.
- `DEBUG=true` or Razorpay webhook without TLS verification on public internet.
- API/workers on Windows in prod.
- Missing Celery **beat** (bookings stick: abandonment, advance TTL, reconfirm, refunds).
- `puja_app` role missing but API connected as superuser (bypasses R12 REVOKE tests).
- Claiming **Phase 3** compliance (Route, splits, deposit, 26Q) — **not in scope** for this MVP.

---

## Sign-off

| Role | Name | Date | GO / NO-GO / GO-with-waivers |
|------|------|------|------------------------------|
| Engineering | | | |
| Ops / infra | | | |
| Product | | | |
| Finance / TDS §0.C | | | |

**Waivers (P1 only):** list ID + reason + expiry.

---

## Quick command block (copy for runbook)

```bash
cd puja_platform && source .venv/bin/activate
export DATABASE_URL='postgresql+psycopg://...'   # superuser for migrate; then puja_app for runtime

alembic upgrade head
for n in 012 013 014 015 016 017 018 019 020 021 022 023 024 025 026 027; do
  python scripts/apply_migration_${n}.py
done
python scripts/apply_migrations_028_032.py
python scripts/bootstrap_puja_app_role.py
python scripts/apply_grants.py
python scripts/check_tds_readiness.py --strict

# runtime (separate units): uvicorn + celery worker + celery beat
```

**Related:** [`OCI_DEPLOYMENT_PLAN.md`](./OCI_DEPLOYMENT_PLAN.md) (Tier A/B on Oracle Cloud) · [`CURSOR_SETUP.md`](../../CURSOR_SETUP.md) · [`TDS_STAGING_ROLLOUT.md`](./TDS_STAGING_ROLLOUT.md) · [`OBSERVABILITY.md`](./OBSERVABILITY.md) (Phase 7 — not MVP blocker).
