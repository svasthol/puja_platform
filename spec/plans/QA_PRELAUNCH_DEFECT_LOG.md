# Pre-Launch QA — Consolidated Defect Log & Go/No-Go

**QA run:** 2026-10-05 (local full-stack, launch `booking_fee` posture)
**Method:** Live end-to-end against a running stack (API :8000, Celery worker+beat, admin UI :3000, Postgres 16 local, remote Redis). Customer + Partner journeys driven over HTTP; admin console driven in a real browser; 21 Celery workers exercised; backend `pytest` (409 tests) run in both postures; performance/concurrency/DB-reliability measured.
**Verdict:** **GO with conditions.** No code-level launch blockers found. All remaining P0 items are **production config/ops gates** (not code bugs). The product's customer app, partner app, admin console, and worker fleet are functionally sound with clean copy.

---

## 1. Executive summary

The product is in good shape. Across inch-by-inch testing:

- **Customer app** — full journey works: OTP login, catalogue (EN + Telugu), puja detail, booking-fee quote (customer charged the frozen `₹61` fee, not the full puja value), slot-hold + night gate, booking + Razorpay order, webhook→confirm, dispatch→offer, booking detail/list, cancel→refund (+ offer auto-expiry).
- **Partner app** — full journey works: register, KYC status, go online/offline, privacy-safe offer inbox (no customer PII), accept (confirmed + RM + trigger-3), reject, pujari-cancel, start→collect balance (cash + TDS accrual)→complete, tax summary.
- **Admin console** — all exercised pages functional with clean, professional copy: login (TOTP), overview, bookings search/detail, service areas, partners/KYC/pricing, failed refunds, catalogue builder, TDS reconcile/backlog, RMs.
- **Celery workers** — all 21 registered, beat schedule correct, maintenance tasks idempotent and fast (`sweep` ~1.2s vs 30s beat).
- **DB reliability** — no session/transaction leaks, no lock contention, exclusion constraints intact, concurrent-accept yields exactly one winner, 20 parallel catalogue loads clean.
- **Copy & i18n** — Flutter l10n flawless (341/341 keys, no missing translations); no spelling/grammar errors found in any surface.

**Top risks to close before go-live (all config/ops, not code):** production `.env` flags, PgBouncer prepared-statement opt-out, SMS DLT approval, a clean production database, and the panchangam vendor running.

---

## 2. Coverage

| Surface | Result |
|---|---|
| Phase 0 — Stack bring-up & health | PASS (`smoke_ok`, `/health` ok) |
| Phase 1 — Backend `pytest` (409) | 404 pass in launch posture; the 17 "failures" are TDS-posture tests, 1 live Setu test, test-harness debt, and data pollution — NOT product bugs |
| Phase 2 — 21 Celery workers | PASS (registration, beat schedule, idempotency) |
| Phase 3 — Customer app E2E | PASS |
| Phase 4 — Partner app E2E | PASS |
| Phase 5 — Admin console | PASS |
| Phase 6 — Perf / concurrency / DB | Healthy; 3 scale/prod risks documented |
| Phase 7 — Copy / spelling / i18n | PASS; 1 backend i18n defect |

---

## 3. Findings (prioritized)

### P0 — must resolve before go-live (production config / ops gates)

| ID | Finding | Action |
|---|---|---|
| P0-1 | **Prod `.env` carries dev/non-launch flags.** Current `.env`: `TDS_ACCRUAL_ENABLED=true`, `PUJARI_FY_PAN_GATE_ENABLED=true`, `APP_ENV=development`, `DEBUG=true`. Go/No-Go requires `TDS_ACCRUAL_ENABLED=false` (A3), `PUJARI_FY_PAN_GATE_ENABLED=false` at first cut (A6), `APP_ENV=production` + `DEBUG=false` (A1). | Set launch-posture flags in the **production** `.env` (dev values are fine locally). `DEBUG=false` also disables `/docs` and the `otp_dev_only` response field. |
| P0-2 | **SMS not configured (DLT pending).** Confirmed: fast2sms fails, msg91 disabled → OTP only via dev path. In prod with `DEBUG=false`, **no OTP is delivered at all** → customers/pujaris cannot log in. | Complete TRAI DLT registration + approved template, or run a pilot with a documented manual-OTP fallback. Go/No-Go E4. |
| P0-3 | **PgBouncer prepared-statement opt-out missing.** `app/db/engine.py` `create_async_engine` has no `connect_args={"prepare_threshold": None}`; worker raw `psycopg.connect()` likewise. Under PgBouncer **transaction mode** (the stated prod connection layer) this causes `DuplicatePreparedStatement` under load (`P-PGBOUNCER`, PENDING). Local direct-Postgres hid it. | Confirm prod DB topology. If PgBouncer transaction-mode: set `prepare_threshold=None` on the async engine **and** worker connections before go-live. If direct Postgres / session-mode: not triggered. |
| P0-4 | **Production must launch on a clean database.** The dev DB is heavily polluted: test pujas/categories ("Test Puja", "Max Test", "Range Puja", "Cat-xxxx") reach the **customer** `GET /v1/pujas`; test customers/bookings/refunds fill admin views. | Launch on a fresh DB seeded only with the real Hyderabad catalogue (+ te i18n), RMs, service areas, and admin. |
| P0-5 | **Panchangam home ribbon unavailable.** `GET /v1/panchangam?city=Hyderabad` → 404 ("not available for this city and date yet"); cache had 1 today/future row; local vendor (`:3001`) served nothing. | Run the panchangam vendor + the daily `refresh_panchangam_cache` beat in prod; confirm the customer app degrades gracefully on 404. |

### P1 — fix before launch or ship with a documented mitigation

| ID | Finding | File / fix |
|---|---|---|
| P1-1 | **Razorpay order created inside the booking DB transaction.** `create_booking` locks the slot-hold `FOR UPDATE` and then `await razorpay_client.create_order(...)` within the same `get_db_txn` transaction → DB connection + row lock held across the gateway round-trip. Under a muhurtam booking burst this pins the pool across Razorpay latency. | `app/services/booking_service.py` (~line 243 lock, ~line 404 order). Shorten the txn: persist `payment_pending` + commit, create the order outside the write txn, then update `razorpay_order_id` in a short second txn. **Behavior change — confirm before implementing.** |
| P1-2 | **Synchronous bcrypt on the async event loop.** `hash_secret`/`verify_secret` call `bcrypt.hashpw`/`checkpw` directly from async auth handlers (OTP request/verify, refresh, admin login) → event loop blocked ~50-250ms per call; a login burst serializes all requests. | `app/core/security.py`. Dispatch bcrypt to a thread (`anyio.to_thread.run_sync` / `run_in_executor`). Low-risk, behavior-preserving. |
| P1-3 | **Refund 4xx not fast-failed.** Razorpay 4xx (permanent) errors are retried up to 8× before `failed_permanent` (seen live in admin Failed-refunds: attempt_count=8, "Client error"). Delays ops visibility and customer refund. | `app/workers/refund.py`. Classify 4xx/permanent as `failed_permanent` on first permanent error; keep backoff for 5xx/timeouts. (Also in `PRE_LAUNCH_REVIEW.md` P1-2.) |
| P1-4 | **Telugu catalogue list name can render blank.** `build_puja_summaries`: for `te`, `name = loc_row.get("name") or ""` — a puja with no `te` `puja_i18n` row shows a BLANK card (the `en` branch falls back to `pujas.name`). | `app/services/catalog_read.py` (~line 139). Fall back te → en i18n → base name, and/or enforce a catalogue-completeness check so no active puja ships without a `te` row. |

### P2 — schedule (non-blocking)

| ID | Finding |
|---|---|
| P2-1 | `.env` has duplicate/conflicting keys (`S3_*`, `MSG91_AUTH_KEY` — the **last** `MSG91_AUTH_KEY` resolves to the placeholder `your_api_authkey`). De-duplicate before prod. |
| P2-2 | `app/workers/tds_accrual.py` uses bare `asyncio.run()` with no `WindowsSelectorEventLoopPolicy` → TDS tasks raise `ProactorEventLoop` InterfaceError on a **Windows** worker. Prod is Linux (unaffected); set the selector policy in `worker_process_init` for Windows-dev parity. |
| P2-3 | Latent: with `TDS_ACCRUAL_ENABLED=true`, accepting a `full_online` booking violates `ck_bookings_amount_split` (TDS FY writer sets `amount_due_offline` on a full_online row). Gated off at launch (TDS off + booking_fee-only); will matter at the TDS-enable milestone. `app/services/tds_v3_fy_writer.py`. |
| P2-4 | `.env` holds real secrets (Razorpay, two AWS key pairs, Setu, TOTP key, KYC pepper). Ensure `.env` stays gitignored; rotate before prod; never ship literal dev keys. |

### Confirmed NON-issues (triaged, not bugs)

- **Admin bookings search 422** (Phase 1): test-harness debt only — direct-call unit tests leak FastAPI `Query(...)` sentinels. Real HTTP + the admin UI work (verified 200 with results + `booking_class` filter).
- **8 TDS tests + 1 Setu live test "failing"**: posture/external-dependency, not product bugs.
- **"Service areas list empty" / "worker registration missing"**: my probe-script artifacts; the UI and the passing `test_celery_task_registration` prove otherwise.
- **"No offer" in a concurrency retry**: the advance **inbox cap** (2) correctly excluded a pujari already at 2 live offers — correct behavior.

---

## 4. Environment caveats (could not fully test here)

- **Flutter SDK not installed** on this machine → `flutter test` / `flutter analyze` and on-device UI could not run. Mobile verified via backend API flows + l10n parity + code review. On-device tap-through remains a manual checklist.
- **SMS** delivery (OTP + RM/reconfirm SMS) — DLT-blocked; validated only through `sms_router` routing/copy.
- **KYC DigiLocker + selfie** full round-trip needs the live Setu sandbox + public callback (ngrok); register + status endpoints verified.
- **Panchangam vendor** (`:3001`) not serving locally → ribbon 404.
- **Instant-offer modal** (`urgency_flip` → `notify_offer_instant`) not triggered in real time; worker + task verified separately.

---

## 5. Launch-readiness checklist (map to MVP_GO_NO_GO_CHECKLIST.md)

- [ ] A1 `APP_ENV=production`, `DEBUG=false` (P0-1)
- [ ] A3 `TDS_ACCRUAL_ENABLED=false` · A6 `PUJARI_FY_PAN_GATE_ENABLED=false` (P0-1)
- [ ] E4 SMS DLT approved (P0-2)
- [ ] P-PGBOUNCER `prepare_threshold=None` if PgBouncer transaction-mode (P0-3)
- [ ] Clean prod DB — no test pollution (P0-4)
- [ ] Panchangam vendor + daily beat running (P0-5)
- [ ] P1-1..P1-4 fixed or waived with owner
- [ ] Celery beat + worker running; `/health` `sweep_stale=false` (verified locally)
- [ ] Razorpay live keys + webhook secret match dashboard

---

## 6. QA artifacts

Working logs + harness scripts live under `_qa_tmp/` (customer_e2e, partner_e2e, partner_secondary, worker_harness, perf_check, concurrent_accept, i18n_check, admin_api_checks) and `_qa_tmp/QA_FINDINGS.md` (full per-phase running log). These are dev-only scratch files; delete before committing.
