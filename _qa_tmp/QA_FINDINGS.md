# Pre-Launch QA — Running Findings Log

Severity: P0 (launch blocker) / P1 (fix before launch or mitigate) / P2 (log + schedule) / OBS (observation).

---

## Phase 0 — Stack bring-up & health

STATUS: PASS (stack up, gate green).

Environment:
- Postgres 16 local :5432, DB `Mana_Guruji` — migrated (alembic head 011 + SQL migrations 012-034 applied; PostGIS + btree_gist present). Richly seeded: 113 pujas, 147 pujaris, 595 users, 126 RMs, 1214 bookings.
- Redis: REMOTE `redis://18.60.87.153:6379/0` — reachable.
- API: controlled uvicorn on :8000 (logs -> _qa_tmp/api.log). `/health` = ok, db:true, redis:true, sweep_stale:false.
- Celery worker + beat: user's running instances (one each; the "duplicate" PIDs were just the Windows console-script parent/child pattern).
- Admin UI: Next dev on :3000, /login = 200.
- Gate: `scripts/dev_api_smoke.py` = `smoke_ok`.

Findings:
- [P1] Prod posture flags set to non-launch values in `.env`: `TDS_ACCRUAL_ENABLED=true` (go/no-go A3 requires false at launch), `PUJARI_FY_PAN_GATE_ENABLED=true` (A6 requires false at first cut). Acceptable for dev/QA (lets us exercise TDS), but MUST be flipped in prod `.env`. Verify at deploy.
- [P2] `.env` config hygiene: duplicate/conflicting keys — `S3_ENDPOINT_URL` (3x, last = empty), `S3_ACCESS_KEY`/`S3_SECRET_KEY`/`S3_BUCKET_KYC`/`S3_REGION` (2x+, last-wins), `MSG91_AUTH_KEY` (2x; LAST value is the placeholder `your_api_authkey`, so msg91 key resolves to a placeholder). Foot-gun; de-duplicate before prod.
- [OBS] SMS not configured (confirmed): fast2sms fails (no DLT), msg91 disabled -> OTP only via dev path (`otp_dev_only` in response + log when `DEBUG=true`). Prod OTP delivery is BLOCKED on DLT approval (go/no-go E4). `otp_dev_only` is correctly gated behind DEBUG (omitted when DEBUG=false) - verify DEBUG=false in prod.
- [OBS -> investigate Phase 3] `checkout/quote` smoke returned `total=460000.00 modes=[]` for its test puja — confirm booking_fee launch model charges only the frozen booking fee (~₹61) via Razorpay and that `total` is informational (full puja value), not the Razorpay charge.
- [P2/security] `.env` carries real secrets (Razorpay test keys, two AWS access/secret key pairs, Setu client secret, TOTP_ENC_KEY, KYC pepper). Ensure `.env` is gitignored (it is referenced as such) and rotate anything that may have leaked; do not ship these literal dev keys to prod.

---

## Phase 1 — Automated suites

STATUS: Backend suite fundamentally healthy; Flutter blocked (not installed).

Backend pytest:
- Default env (TDS flags ON as in .env): 388 passed, 21 failed, 12 errors.
- LAUNCH posture (TDS_ACCRUAL_ENABLED=false, FY-PAN gate off): **404 passed, 17 failed, 6 skipped** (12 errors disappear).
- Triage of the 17 launch-posture failures:
  - 8 are TDS-only tests that REQUIRE TDS=on to pass (test_sprint2_tds_launch_e2e x4, test_booking_fee_launch_e2e tds, test_admin_slice3 tds dispute, test_admin_tds_compliance, test_export_tds_26q). Not product bugs - posture-dependent.
  - 1 live external dependency: test_kyc_digilocker_live (hits Setu sandbox + ngrok). Environmental.
  - 4 TEST-HARNESS DEBT (not product bugs): admin_bookings search x3 + admin_catalog content_replace. Root cause = unit tests call FastAPI endpoint functions DIRECTLY without passing params that default to `Query(...)`, so the Query sentinel leaks (`booking_class must be instant or advance` 422; `cannot adapt type 'Query'` with `locale=Query(en)`). Through real HTTP FastAPI resolves these to None/defaults and the endpoints work. Verify via admin console in Phase 5.
  - 2 shared-DB data pollution: test_wave1 dispatch (online pujaris lack pujari_pricing for the slot -> 0 offers; dispatch logged the reason correctly) and dispatch_immediate (actually produced offers=1 in log; timing/data assertion).
  - 1 customer_catalog i18n (test_list_pujas_locale_te_vs_en): surfaced REAL issues below.
  - (admin_slice2 refund_support_within_cap: flips between error/failure across runs - shared refund-cap state pollution; verify via console.)
- "12 errors" in the default run were shared-DB test-isolation/ordering noise + TDS interaction: 2 sampled (admin_slice2 manual_reassign, launch_reconfirm ping) PASS in isolation.

Real product findings from Phase 1:
- [P1] i18n name fallback: `GET /v1/pujas?locale=te` returns `name=""` (empty string) for pujas with no Telugu translation, instead of falling back to the English/base name. In the Telugu UI this renders a BLANK puja name. Confirmed via live API: real puja griha-pravesham shows 'గృహప్రవేశం' correctly, but any puja lacking a te row returns "". Fix: COALESCE te_name -> base name, never empty. (Confirm resolver in Phase 7.)
- [P1/data] Catalog pollution reaches the customer API: `GET /v1/pujas` returns test pujas ('Premium Puja','Test Puja','Max Test','Range Puja','Resolver Test', etc.) and test categories ('Cat-b6434491'...) - several with EMPTY slug and empty te name - ranked ABOVE real pujas. Dev-DB only, but (a) prod MUST launch on a clean DB (no test seed), and (b) consider a guard so blank-name / blank-slug / is_active rows can never surface in catalog.
- [P2 -> P1 at TDS-enable milestone] Latent constraint bug: with TDS_ACCRUAL_ENABLED=true, accept_offer on a `full_online` booking violates `ck_bookings_amount_split` (TDS FY writer in tds_v3_fy_writer.py sets amount_due_offline on a full_online row). Gated off at launch (TDS off + booking_fee-only), but will break if TDS is enabled while full_online exists. File: app/services/tds_v3_fy_writer.py:114.

Flutter:
- [BLOCKER-for-mobile-QA] Flutter SDK NOT installed on this machine (no flutter.bat found in PATH or common dirs). Cannot run `flutter test` / `flutter analyze`. 15 widget/unit tests exist but can't be executed here. Mobile apps (customer + partner) will be QA'd via: (a) their backend API flows end-to-end, and (b) code-level screen-logic + copy review of lib/features/*. On-device/emulator interactive testing remains a manual checklist.

---

## Phase 2 — Celery workers (21 tasks)

STATUS: Workers healthy. Registration + beat schedule correct; all maintenance tasks idempotent + fast. One Windows-dev-only async bug; environment notes.

Registration + schedule:
- All 9 beat entries present and correct: sweep 30s, refresh-advance-offers 5m, escalate-urgency 2m, rm-escalation-scan 15m, process-refunds 60s, refresh-panchangam 1h, expire-kyc 5m, process-tds-accrual-intents 60s, sweep-never-collected-tds 6h.
- test_celery_task_registration.py PASSED in the suite (all 21 task paths register when the worker imports its `include=` modules). (My ad-hoc harness showed "MISSING" only because it checked `celery_app.tasks` without importing the task modules first - harness artifact, not a product issue.)

Live idempotent invocation (each run x2 against live DB):
- sweep.run_sweep: OK x2, duration ~1.1-1.2s (far under the 30s beat -> no overlap risk; good Phase 6 signal). All counts 0 on the quiet DB.
- advance_offers.refresh_advance_offers: 11 -> 11 (idempotent in-place TTL UPDATE).
- urgency_flip.escalate_urgency_on_threshold: [] x2.
- rm_escalation.scan_rm_escalations: {no_accept:[],approaching:[]} x2.
- kyc.expire_kyc_requests: 0 x2; run_kyc_maintenance: {expired:0, pending_docs_gauge:50, stale_artifact_rows:12}.
- reconfirmation.process_reconfirm_pings / escalations: [] (clean).
- no_show.flag_stuck_confirmed_bookings: [] (clean).
- refund.process_refunds(3): {processed:0, picked:0} - correct: all 90 pending refunds have next_attempt_at in the future (backoff).
- tds.process_tds_accrual_intents(5): {processed:0,parked:0,failed:0,reconciled:0} - no pending intents.
- panchangam.refresh_panchangam_cache: {skipped:False, fetched:0} - handled vendor-down gracefully (no crash).

Dispatch (broadcast/rebroadcast/direct) + 9 notification tasks: exercised live in Phase 3/4 booking E2E (broadcast -> notify_offers; accept -> notify_accept_ack; cancel -> notify_offer_withdrawn) and covered by existing tests (test_phase2_notifications passed; test_launch_reconfirm passes in isolation).

Findings:
- [P2, Windows-dev-only] `app/workers/tds_accrual.py` calls bare `asyncio.run(...)` with no `WindowsSelectorEventLoopPolicy`. On Windows the default ProactorEventLoop breaks psycopg async -> `sweep_never_collected_tds` raised `psycopg.InterfaceError: cannot use ProactorEventLoop`. `process_tds_accrual_intents` only survived because it had 0 intents; with real intents it would also fail on Windows. PROD IS LINUX (go/no-go B1 bans Windows workers), where asyncio.run uses SelectorEventLoop by default -> no issue. Fix (low-risk, improves Windows-dev parity): set the selector policy in a `worker_process_init` handler in celery_app.py. File: app/workers/tds_accrual.py:23,41.
- [OBS/data] Refund backlog in dev DB: 90 pending / 52 failed_permanent / 30 succeeded (was 47/4/9 in Sept review). Growth is mostly test pollution + invalid gateway_txn_ids, but reinforces the KNOWN code issue (PRE_LAUNCH_REVIEW P1-2): Razorpay 4xx errors are retried up to 8x instead of being classified failed_permanent on first permanent error. Confirm in Phase 6/refund review. Prod clean DB avoids the backlog; the classification fix is still recommended.
- [OBS/dev] Panchangam cache stale locally: 101 rows but only 1 for today/future; local vendor (127.0.0.1:3001) not serving (`fetched:0`). Customer home ribbon will be sparse in dev. Prod requires the panchangam vendor running + the daily beat. Verify ribbon in Phase 3.
- [OBS] run_kyc_maintenance reports 12 stale KYC artifact rows (expired past retention; S3 purge deferred to ops runbook per design) - ops cleanup item, not a bug.

---

## Phase 3 — Customer app E2E

STATUS: PASS - full customer journey works end-to-end (launch booking_fee flow), live against the running API.

Verified (each OK):
- OTP dev login (customer) -> access token.
- GET /v1/pujas 200; GET /v1/pujas/{id} 200 -> real puja 'Griha Pravesham' localized name 'గృహప్రవేశం', 5 content items, 4 addons. i18n works for seeded pujas.
- GET /v1/checkout/quote 200 -> booking_fee model CONFIRMED: total_amount=4200 (informational full puja value) but razorpay_amount=61.00 (what the customer is actually charged), booking_fee=61, label "Muhurat & Slot Lock Token", payment_mode=booking_fee. RESOLVES the Phase 0 "total=460000" question - that was the informational total for a polluted test puja, not a charge.
- POST /v1/slot-holds 201 -> advance/instant classification correct; idempotent slot via ux constraint.
- Night gate CONFIRMED: near-term (2h) night slot -> class=instant + gate_warning INSTANT_NIGHT_BLOCKED ("Instant bookings are not available for night slots (12:00 AM-5:59 AM). Please choose a later time."). Advance night slots correctly allowed (muhurtam).
- POST /v1/bookings 201 -> Razorpay order created (order_...), booking_class frozen=advance, razorpay_amount=61.
- Idempotent duplicate booking: same slot -> 409 with existing checkout payload (correct).
- POST /v1/webhooks/razorpay (signed) 200 -> {"result":"confirmed"}; booking -> requested; paid_at set.
- Dispatch live: running sweep created the offer in round 1 (offers=1, status=offered); my manual broadcast round 2 correctly deduped (pujari already has live offer -> excluded). notify_offers fired -> notification row ('pujari','New puja offer'). Proves dispatch.broadcast_booking + sweep + notify_offers workers end-to-end.
- GET /v1/bookings/{id} 200 -> status, payment breakdown, history=['requested']. GET /v1/bookings list 200.
- POST /v1/bookings/{id}/cancel 200 -> status=cancelled, refund_amount=61.00 (100% booking fee, before-24h policy), refund_eta "5-7 business days"; refund row inserted (pending); pending offer auto-EXPIRED on cancel (P-CANCEL-OFFERS-SYNC working); notify_offer_withdrawn enqueued.

Copy captured (for Phase 7 cross-check): booking_fee_label "Muhurat & Slot Lock Token"; offer push title "New puja offer"; refund_eta "5-7 business days"; night-gate message as above. All clean en copy.

Findings:
- [P1] Panchangam home ribbon unavailable: GET /v1/panchangam?city=Hyderabad -> 404 "Panchangam not available for this city and date yet." Cache has only 1 today/future row and the local vendor (127.0.0.1:3001) serves nothing. For launch: the panchangam vendor + daily refresh beat MUST be running or the customer home ribbon 404s. Verify the customer app degrades gracefully on 404 (code review Phase 7). Prominent home feature -> treat as launch-readiness P1 (ops/config, not core code bug).
- [OBS] Booking list showed a lingering 'requested' booking alongside 'cancelled' across reruns - consistent with the idempotent-duplicate path; not a bug, but confirms idempotency returns a prior row.

---

## Phase 4 — Partner app E2E

STATUS: PASS - full partner journey works end-to-end, live against the running API.

Verified (each OK):
- Pujari OTP dev login (app_context=pujari).
- Go online: PUT /v1/me/heartbeat 200 {status:ok} -> Redis presence set; FY-PAN gate allowed (pujari under FY5L threshold even with PUJARI_FY_PAN_GATE_ENABLED=true).
- GET /v1/offers 200 -> offer card fields: assignment_id, booking_id, puja_name, scheduled_date/time, area_label, payment_mode, total_amount, amount_due_offline, booking_class, urgency, urgency_escalated. PRIVACY CONFIRMED: NO customer phone or address exposed (area label 'QA Zone' only), per §21.4.
- POST /v1/offers/{id}/accept 200 -> booking CONFIRMED, pujari_id set (trigger 3), relationship_manager auto-assigned. notify_accept_ack fired -> notification ('pujari','Added to your Bookings').
- POST /v1/offers/{id}/reject 200 -> {status:rejected, enqueue_rebroadcast:<booking>}; assignment=rejected; rebroadcast enqueued.
- POST /v1/bookings/{id}/pujari-cancel 200 -> booking back to 'requested', pujari_id cleared (sanctioned NULL), rebroadcast.
- GET /v1/pujari/bookings (list) 200 count=1; GET /v1/pujari/bookings/{id} 200 -> status=confirmed, RM present, NO raw customer phone (launch policy: RM-mediated contact).
- Service lifecycle: POST start 200 -> in_progress; POST confirm-balance-collected {method:cash} 200 -> collected ₹4200, TDS accrual intent queued (accrual_enabled:true, message 'TDS accrual queued'); POST complete 200 -> completed (gate enforced full balance collected first). DB final: completed, collected_amount=4200, method=cash.
- GET /v1/me/tax-summary 200 -> fy_start 2026-04-01, fy_gross_facilitation 4200 (updated after collection), tds_accrued 0, individual_fy_threshold 500000, pan_warn 450000.
- DELETE /v1/me/heartbeat go-offline 200 {status:offline}.
- Onboarding: POST /v1/pujari/register 200 -> {verification_status:pending, created:true}; GET /v1/pujari/kyc/status 200 -> required docs [identity_proof, address_proof, photo].

This validated workers live: dispatch.broadcast_booking, sweep, notify_offers, notify_accept_ack, offer accept (sibling supersede + RM assign), tds_accrual (intent on collection), rebroadcast (on reject/pujari-cancel).

Copy captured: accept-ack push "Added to your Bookings".

Findings:
- [OBS] Full KYC DigiLocker + selfie flow requires the live Setu sandbox + public callback (ngrok KYC_REDIRECT_URL). register + kyc/status endpoints work; the vendor round-trip is covered by the live e2e test (test_kyc_digilocker_live) which needs the external dependency up. Not testable headless here.
- [OBS] Instant-offer modal path (urgency_flip -> notify_offer_instant) not triggered live (needs an advance booking crossing the instant lead window in real time). The urgency_flip worker itself ran idempotently in Phase 2; the notify_offer_instant task is registered + covered by test_phase2_notifications.
- [OBS] On accept, only pujari-context notifications were written for the booking ('Added to your Bookings'); customer-facing confirmation appears to rely on WS/booking-status refresh rather than a push row. Confirm this is intended (customer may expect a 'booking confirmed' push).

---

## Phase 5 — Admin console (Ops Console)

STATUS: PASS - admin console is functional and well-designed; clean professional copy throughout; no console errors or broken pages observed.

Admin auth: TOTP login works (generated code from decrypted secret). Login page copy clean ("SMS OTP is not used for staff. Use the 6-digit code from Google Authenticator / Authy.").

API-level admin checks (via admin token):
- GET /v1/admin/bookings 200 (20 results); ?status=confirmed 200; ?booking_class=advance 200 -> RESOLVES Phase 1: admin bookings search works via real HTTP; the Phase 1 422 failures were test-harness bugs only.
- GET /v1/admin/bookings/{id} 200 (detail); /v1/admin/refunds requires ?status (422 without it, 200 with); /v1/admin/pujaris 200; /v1/admin/relationship-managers 200 (143); /v1/admin/promos 200; /v1/admin/tds/fy-reconcile 200 {green,rows}; /v1/admin/tds/compliance-backlog 200.
- (service-areas "list_len=0" in my API probe was a PROBE bug - I didn't read the 'areas' key; the UI shows areas correctly.)

Browser-driven pages (visually verified, screenshots captured):
- Overview: Session card (TOTP, ADMIN role), "Available now" feature cards, full left nav. OK.
- Bookings: search form (phone/id/status/date range) + Results table (status badges, customer+phone, puja, schedule, 360-degree detail links). Live search returned real rows incl. my QA bookings. OK.
- Service areas: "Display label at launch - dispatch stays citywide" + Add-area form + list (Active Zone: Hyderabad, 13 pujaris, 11 active bookings, ACTIVE). OK.
- Partners: "Pujari directory, KYC review, and per-puja pricing" + search + KYC queue link + list (my QA Pujari VERIFIED 122 priced; New User PENDING). OK.
- Failed refunds: "failed_permanent queue - 20 item(s) need ops attention" with Booking/Customer/Amount/Reason/Attempts/Error. Visibly shows rows at Attempts=8 with "Client error" (4xx) - direct confirmation of the refund 4xx-classification issue below.
- Catalogue builder: "28 categories" with ON/OFF toggles + reorder; policy note (soft-delete, is_active=false, customer reads active only). "Test Cat" OFF.

Findings:
- [P1] Refund 4xx classification (confirmed visibly in admin Failed refunds): multiple refunds reached attempt_count=8 with "Client error" (Razorpay 4xx) before going failed_permanent. Per PRE_LAUNCH_REVIEW P1-2, 4xx/permanent gateway errors should be classified failed_permanent on the first permanent error, not retried 8x. File: app/workers/refund.py. (Dev backlog is also inflated by pollution; prod clean DB mitigates volume but the classification fix stands.)
- [P2/data] Catalogue + categories pollution visible in admin: test categories/pujas ("Test Cat", and from Phase 1 "Cat-xxxx", "Test Puja", "Max Test", "Range Puja") exist in the catalogue. Soft-delete model is sound; prod must launch on a clean catalogue (disable/remove all test rows) so they never reach GET /v1/pujas.
- [OBS/UX] Every hard URL navigation re-runs "Verifying session..." (client-side session verify). Minor; SPA link-nav avoids it. Not a bug.
- [OBS] /v1/admin/refunds requires the `status` query param (422 if omitted) - ensure the admin UI always supplies it (the UI does; it defaults to the failed_permanent queue).

---

## Phase 6 — Performance, concurrency & DB reliability

STATUS: DB is healthy at rest and under light concurrency. Three code-level risks for scale/prod (none are launch blockers at single-city volume, but all should be addressed before scale; one is a prod-config gate).

Runtime measurements (local, DEBUG=true so SQL-echo inflates latency; prod DEBUG=false is faster):
- Hot endpoint latency (warm, 25x): GET /v1/pujas?limit=20 p50=54ms p95=64ms; GET /v1/pujas/{id} p50=18ms p95=33ms; GET /checkout/quote p50=12ms p95=12ms. All fine for launch.
- Concurrency: 20 parallel GET /v1/pujas -> 20/20 OK in ~1.0s, zero errors (pool 10+5 handled it; no DuplicatePreparedStatement locally since direct Postgres).
- DB activity snapshot: pg_stat_activity active=1 idle=12; idle_in_transaction=0; ungranted_locks (waiters)=0; transactions_open_gt_5s=0. NO session/transaction leaks, no lock contention at rest.
- Sweep duration ~1.1-1.2s vs 30s beat (Phase 2) -> no overlap/pile-up risk.
- Double-booking prevention: both exclusion constraints present (ex_bookings_pujari_no_overlap, ex_bookings_intended_no_overlap); LG concurrency tests PASS in launch posture (test_lg_duration_overlap_accept + _concurrent) -> concurrent-accept yields exactly-one-winner. Advance inbox cap enforced (observed: pujari at 2/2 live offers correctly excluded from new dispatch).

Findings (code-level, proposed fixes - NOT auto-applied; invariants/constraints are off-limits):
- [P1] Synchronous bcrypt on the async event loop. app/core/security.py hash_secret/verify_secret call bcrypt.hashpw/checkpw directly (CPU-bound, ~50-250ms) and are invoked from async auth handlers (otp_request, otp_verify, refresh, admin_login). Each call BLOCKS the event loop for every concurrent request. At single-city launch volume tolerable; under a login burst it serializes all requests -> latency spikes. Fix: dispatch bcrypt to a thread (anyio.to_thread.run_sync / loop.run_in_executor). Low-risk, behavior-preserving.
- [P1] Razorpay order created INSIDE the booking DB transaction. app/services/booking_service.create_booking runs under get_db_txn (one transaction for the whole request); it takes `SELECT ... FOR UPDATE` on the slot_hold (line ~243) and later `await razorpay_client.create_order(...)` (line ~404) WITHIN that transaction. The DB connection + hold row lock are held across the Razorpay network round-trip (hundreds of ms, or up to the Razorpay timeout on error). Under a muhurtam booking burst this pins pool connections across gateway latency -> pool exhaustion at modest concurrency (PgBouncer server-connection pinned per in-flight booking). Fix: shorten the transaction - create the payment_pending booking + commit, create the Razorpay order OUTSIDE the write txn, then update razorpay_order_id in a second short txn (idempotent-safe). Behavior change -> propose + confirm before implementing.
- [P0-for-prod IF PgBouncer transaction-mode] Missing prepared-statement opt-out. app/db/engine.py create_async_engine has NO connect_args={"prepare_threshold": None}; worker raw psycopg.connect() (sweep.get_connection) also does not set it. project.mdc states PgBouncer is the prod connection layer. Under PgBouncer transaction mode, psycopg3 server-side prepared statements cause DuplicatePreparedStatement under load (P-PGBOUNCER, PENDING). Local direct-Postgres hid this (20 concurrent OK). ACTION: confirm prod DB topology; if PgBouncer transaction mode, set prepare_threshold=None on the async engine AND worker connections before go-live (treat as P0). If prod connects directly to Postgres (no PgBouncer) or session-mode pooling, this is not triggered.
- [OBS] Connection-budget math for prod: per API instance = pool_size 10 + overflow 5 = 15; each Celery prefork child = 1 raw sync psycopg conn per running task; + beat. Ensure PgBouncer default_pool_size / Postgres max_connections >= (API_instances*15) + (sum worker concurrency) + beat, with headroom for the muhurtam burst. Name it in the deploy runbook.
- [OBS] SQLAlchemy echo=settings.DEBUG. In dev (DEBUG=true) every statement is logged (perf + noise). Prod DEBUG=false disables it - fine; just ensure DEBUG=false in prod (also gates /docs and otp_dev_only).

---

## Phase 7 — Copy / spelling / grammar / i18n audit

STATUS: Copy quality is HIGH across all surfaces. Mobile i18n is effectively flawless. One backend i18n code defect (te blank name) + catalogue data completeness.

Flutter localization (lib/l10n/app_en.arb vs app_te.arb):
- 341 keys in EN, 341 in TE. ZERO missing in either direction. Only 1 string identical across locales: kycDigilockerAppBar = "DigiLocker" (government brand name - correctly identical, not a defect). Excellent i18n coverage.

Backend / API / admin copy (captured during E2E, all clean + professional):
- booking_fee label "Muhurat & Slot Lock Token"; night-gate "Instant bookings are not available for night slots (12:00 AM-5:59 AM). Please choose a later time."; refund eta "5-7 business days"; offer push "New puja offer"; accept-ack "Added to your Bookings"; admin login "SMS OTP is not used for staff..."; catalogue policy note; service-areas "Display label at launch - dispatch stays citywide"; bookings "PII reads are audited". No spelling/grammar errors found in any exercised surface.
- Telugu catalogue content verified live: category names (వ్రతాలు, గృహప్రవేశం మరియు వాస్తు, సంస్కారాలు, హోమాలు, ...), puja name గృహప్రవేశం - correct Telugu script.

Findings:
- [P1] te list-name empty fallback (CONFIRMED in code): app/services/catalog_read.py build_puja_summaries line ~139: `if loc == "te": name = loc_row.get("name") or ""`. A puja with no `puja_i18n` (te) row renders a BLANK name in the Telugu customer catalogue list (the en branch falls back to base `pujas.name`; te returns ""). The list query also fetches only the te row (no te->en chain, unlike categories which COALESCE te->en). Fix options: (a) fall back te -> en i18n -> base name (defense-in-depth, avoids blank cards), and/or (b) enforce a catalogue-completeness check so no active puja ships without a te i18n row. At launch on a clean catalogue where every puja has te i18n, this does not trigger - but it is a real blank-card risk and should be hardened.
- [P2/data] Related: the blank te names observed in Phase 1/3 were all test-pollution pujas (no i18n rows). Clean prod catalogue + the fallback fix together close this.
- [OBS] No spelling, grammar, or wrong-copy issues found in the admin console, API messages, notification bodies, or Flutter localization that I exercised. Copy is consistently professional.
