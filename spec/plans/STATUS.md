# Development status tracker

**Single source of truth for implementation progress.** Update this file in the same
change as every completed task. Details and acceptance criteria: track files
(`PLATFORM.md`, `CUSTOMER.md`, `PARTNER.md`, `ADMIN.md`, `OBSERVABILITY.md`). Phase order and exit
gates: [`MASTER.md`](./MASTER.md).

**Track files do NOT carry `Status:` fields** (removed 2026-07-18 — they drifted against
this file on every task). Status changes happen here and only here; track files own
Spec / Files / Acceptance / Depends-on.

**Last audited:** 2026-08-10 (cancel UX + `P-CANCEL-OFFERS-SYNC`; `P-FCM-CUSTOMER-CANCEL` IN_PROGRESS) · **pytest:** `test_launch_slice.py::test_list_offers_excludes_customer_cancelled_booking` added; run full `pytest tests/ -q` after clean seed

---

## Puja MVP launch (SPEC_AMENDMENTS §21)

Policy: `spec/plans/LAUNCH_POLICY.md`.

| ID | Status | Notes |
|---|---|---|
| P-LAUNCH-NO-DIRECT | COMPLETED | Block direct at API; webhook always broadcast |
| P-LAUNCH-DISPATCH | COMPLETED | Citywide + deferred windows + status-aware re-offer |
| P-LAUNCH-HEARTBEAT | COMPLETED | GPS-optional presence |
| P-LAUNCH-BUFFER | COMPLETED | Soft 60m — eligibility + accept only |
| P-LAUNCH-AREA | COMPLETED | `service_area_id` on addresses + `GET /service-areas` + admin CRUD |
| P-LAUNCH-RM | COMPLETED | RM CRUD + assign on accept + customer/pujari booking expose |
| P-LAUNCH-PUJARI-BOOKING | COMPLETED | `GET /pujari/bookings` + `GET /pujari/bookings/{id}` |
| P-LAUNCH-OFFERS | COMPLETED | `area_label`, puja, schedule on offer cards |
| P-LAUNCH-RECONFIRM | COMPLETED | 24h ping + 4h RM escalation via sweep |
| MIG-012 | COMPLETED | Launch policy schema — `scripts/apply_migration_012.py` |
| MIG-013 | COMPLETED | Reconfirmation schema (§21.7) — `spec/db/migration_013.sql` |

**§21 backend in this repo:** all rows above through `P-LAUNCH-RECONFIRM` are **COMPLETED**.
Mobile clients tracked separately below (`mana_guruji_mobile` — partner **IN_PROGRESS**, customer **IN_PROGRESS**).

### Dispatch v2 (SPEC_AMENDMENTS §21.6.A–H)

Policy merged into `SPEC_AMENDMENTS.md` §21.6.A–H, `DISPATCH_FLOW.md`, `LAUNCH_POLICY.md`,
`PARTNER.md`, `CUSTOMER.md`, `API_CONTRACTS.md`, `DATABASE.md`, `project.mdc` (July 2026, v4.1 review).
**Backend DV2 rows below are COMPLETED** unless marked otherwise.

| ID | Status | Notes |
|---|---|---|
| P-LAUNCH-DISPATCH-V2 | COMPLETED | Umbrella — immediate dispatch, dual UX, frozen `booking_class`, night 2a; DV2 rows shipped |
| MIG-014 | COMPLETED | `spec/db/migration_014.sql` — `booking_class`, superseded seed, dispatch escalation cols, DV2 settings, trigger 3 sibling supersede |
| MIG-015 | COMPLETED | `booking_no_show_alerts` — P-SWEEP-CONFIRMED ops alert idempotency |
| MIG-016 | COMPLETED | `ops_monitor_alerts` — P-MONITOR unified alert store |
| MIG-017 | COMPLETED | `panchangam_daily` — §23 server-cached panchangam (`spec/db/migration_017.sql`) |
| MIG-018 | COMPLETED | Panchangam home-ribbon columns — §23.6 (`spec/db/migration_018.sql`) |
| DV2-BOOKING-GATE | COMPLETED | §21.6.A — `booking_class` + night 422s at `POST /v1/bookings`; advisory warnings on `POST /slot-holds` |
| DV2-SUPERSEDE | COMPLETED | §21.6.B — sibling-offer resolution in trigger 3 (`superseded` + `responded_at`); `LG-sibling-supersede` |
| DV2-IMMEDIATE | COMPLETED | §21.6.C — webhook no longer writes `booking_dispatch_state`; worker `ensure_dispatch_windows()` + class-aware TTL |
| DV2-ADVANCE-TTL | COMPLETED | §21.6.D — sweep step-3 carve-out + `refresh_advance_offers` beat (in-place UPDATE, status-guarded); `tests/test_advance_ttl.py` |
| DV2-URGENCY-FLIP | COMPLETED | §21.6.E — `escalate_urgency_on_threshold` beat + live `urgency`/`urgency_escalated` on `GET /v1/offers`; `tests/test_urgency_flip.py` |
| DV2-RM-ESCALATION | COMPLETED | §21.6.F — `rm_escalation_scan` beat + idempotent `rm_escalated_*` markers; `tests/test_rm_escalation.py` |
| DV2-INBOX-CAP | COMPLETED | §21.6.G — G1 cap at broadcast build; instant offers never suppressed |
| DV2-PARTNER-UX | COMPLETED | §21.6.H — `offer_advance`/`offer_instant` at broadcast + `accept_ack` on advance accept; `tests/test_partner_ux.py` |
| DV2-QUIET-HOURS | COMPLETED | §21.6.H — quiet-hours ping shift + escalation clamp; `tests/test_quiet_hours.py` |
| DV2-DURATION-CI | COMPLETED | §21.6.H — `tests/test_duration_ci.py` (seed + `STRICT_CATALOG_CI` full-table gate, `ck_pujas_duration_pos`, LG-duration-overlap-accept) |

---

## Mobile apps — Flutter (`mana_guruji_mobile`)

Customer + partner apps share one Flutter codebase (build flavors). Repo:
`mana_guruji/mana_guruji_mobile`. Contract: `spec/MOBILE_FLUTTER.md`, `spec/MOBILE_FIREBASE.md`.

| ID | Status | Notes |
|---|---|---|
| C-FLUTTER-CUSTOMER | IN_PROGRESS | Waves 0–4 + bookings + **cancel UX** shipped (2026-08-09). Next: **Wave 4 customer FCM** or panchangam ribbon QA. |
| P-FLUTTER-PARTNER | IN_PROGRESS | **Core slice done** (auth, online, offers, bookings, cancel UX, FCM handlers, l10n). **IN_PROGRESS:** FCM sound QA, **`P-FCM-CUSTOMER-CANCEL`**. **HOLD:** availability, register/KYC, earnings. |
| C-LAUNCH-UX | IN_PROGRESS | **Alias → `P-FLUTTER-PARTNER`** (Offers vs Bookings tabs, §21.9); keep ID for cross-ref |

### Customer app — progress (`C-FLUTTER-CUSTOMER` sub-track)

| ID | Status | Notes |
|---|---|---|
| C-FLUTTER-SHELL | COMPLETED | OTP (`app_context=customer`), `go_router`, bottom nav shell, l10n toggle |
| C-FLUTTER-PANCHANGAM | IN_PROGRESS | Home ribbon → `GET /v1/panchangam`; on-demand cache fill on API miss; app sends IST `date` + locale fallback; device QA after rebuild |
| C-FLUTTER-CATALOG | COMPLETED | Home + list + detail verified on physical device (2026-08-05); `CATALOG_SYNC.md` |
| C-FLUTTER-ADDR | COMPLETED | Address CRUD + map pin + GPS + `service_area_id` verified on physical device (2026-08-05) |
| C-FLUTTER-CHECKOUT | COMPLETED | hold → quote → Razorpay → confirming poll; **Wave 1 #3 E2E** pay → `requested` → partner accept → `confirmed` device-verified (2026-08-06); runbook `mana_guruji_mobile/test/WAVE1_DISPATCH_E2E.md` |
| C-FLUTTER-BOOKINGS | COMPLETED | list + detail + class-aware tracking + RM; **cancel UX** shipped (`C-FLUTTER-CANCEL` 2026-08-09) |
| C-FLUTTER-CANCEL | COMPLETED | `POST /v1/bookings/{id}/cancel` on detail — status-aware dialog + refund snackbar |
| C-FLUTTER-FCM | PENDING | customer push handlers (Wave 6) |

### Partner app — progress (`P-FLUTTER-PARTNER` sub-track)

| ID | Status | Notes |
|---|---|---|
| P-FLUTTER-AUTH | COMPLETED | OTP login (`app_context=pujari`); session refresh; sign-out clears Riverpod + FCM; optional follow-up: 401 refresh failure → force signedOut UI |
| P-FLUTTER-ONLINE | COMPLETED | Toggle → `PUT/DELETE /v1/me/heartbeat` + 30s poll; sign-out calls `goOffline()` when online (2026-08-03) |
| P-FLUTTER-OFFERS-UX | COMPLETED | Inbox + instant sheet + accept/reject + 409/410; FCM + 20s poll; **410 → refresh inbox**; offline instant FCM → snackbar only — device QA via `P-FLUTTER-E2E-SMOKE` |
| P-FLUTTER-BOOKINGS | COMPLETED | List + detail + lifecycle + reconfirm; **pujari-cancel** → Offers tab + rebroadcast (`P-FLUTTER-PUJARI-CANCEL` 2026-08-09) |
| P-FLUTTER-PUJARI-CANCEL | COMPLETED | `POST /pujari-cancel` from detail + reconfirm card; navigates to Requests + refreshes offers |
| P-FLUTTER-FCM-REGISTER | COMPLETED | `POST /v1/me/devices`; Firebase partner flavor; token refresh on Pixel 10 |
| P-FLUTTER-FCM-HANDLERS | COMPLETED | All 5 partner types routed (`offer_instant`, `offer_advance`, `reconfirm_*`, `accept_ack`); foreground + tap; `test/fcm_message_parser_test.dart` |
| P-FLUTTER-FCM-CUSTOMER-CANCEL | IN_PROGRESS | **`P-FCM-CUSTOMER-CANCEL`** — handle `offer_withdrawn` FCM; refresh/dismiss instant modal. Safety nets shipped: poll + 410 refresh (`P-CANCEL-OFFERS-SYNC`) |
| P-FLUTTER-FCM-SOUND | IN_PROGRESS | Native channel + `OfferAlertSound` + FCM sound dedup (2026-08-09). Device sign-off: `mana_guruji_mobile/test/PARTNER_FCM_SOUND.md` C1–C4 |
| P-FLUTTER-L10N | COMPLETED | Partner shell + **OTP auth screen** EN/TE; `LocaleToggleBar` on login |
| P-FLUTTER-DEV-NETWORK | COMPLETED | Physical device: `adb reverse tcp:8000` or LAN IP + `uvicorn --host 0.0.0.0` |
| P-FLUTTER-E2E-SMOKE | IN_PROGRESS | **A, B, D, E — PASS** (2026-08-03). **C1–C4** via `test/PARTNER_FCM_SOUND.md`; checklist: `test/PARTNER_E2E_SMOKE.md` |
| P-FLUTTER-AVAILABILITY | HOLD | Weekly hours + date blocks UI — backend ready (`B-AVAIL`/`B-UNAVAIL`); unblock when onboarding track starts |
| P-FLUTTER-REGISTER | HOLD | Onboarding UI — blocked on eKYC vendor decision + `B-REGISTER` |
| P-FLUTTER-KYC | HOLD | KYC upload/status UI — blocked on eKYC vendor decision + `B-KYC` |
| P-FLUTTER-EARNINGS-UI | HOLD | Header earnings strip — blocked on Phase 3 `B-EARNINGS` / `P-SPLITS` |

**Phase 2 FCM:** `P-FCM-E2E` **IN_PROGRESS** (partner sound device QA — `test/PARTNER_FCM_SOUND.md`). **`P-FCM-CUSTOMER-CANCEL` IN_PROGRESS** — partner push on customer cancel (`offer_withdrawn`). Customer FCM **PENDING** (`C-FLUTTER-FCM`).

**Partner polish (Aug 2026):** FCM sound device sign-off → **`P-FCM-CUSTOMER-CANCEL`** → then availability/register/KYC/earnings HOLD bucket.

---

## Status vocabulary (use exactly one per row)

| Status | Meaning | When to use |
|---|---|---|
| **COMPLETED** | Done; acceptance criteria met | Code merged + verified |
| **IN_PROGRESS** | Actively being worked this sprint | Someone owns it now |
| **PENDING** | Not started; on the roadmap | Default for planned work |
| **BLOCKED** | Cannot start until dependency resolves | Note `blocked_by` in Notes |
| **SKIPPED** | Explicitly out of scope for this release | Note reason (product/policy) |
| **HOLD** | Code may exist; frozen until named unblock task | Do not QA or ship; note unblock condition in Notes |

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
| **2** | Notifications | **IN_PROGRESS** | Backend done; live SMS blocked on DLT; partner FCM handlers **COMPLETED**; `P-FCM-E2E` + `P-FLUTTER-FCM-SOUND` QA pending |
| **3** | Money pipeline | **ON HOLD** | CA memo + Razorpay Route → migration 007, splits, TDS, payouts |
| **4** | Admin control plane | **IN_PROGRESS** | 4-0 + 4A + 4B + **4C COMPLETED** (manual QA 2026-07-22); partner Flutter **IN_PROGRESS** (`mana_guruji_mobile`); remaining Phase 4 exit gate items in ADMIN.md (4B catalogue/KYC smoke) |
| **5** | Scheduled-booking ops | **COMPLETED** | B-CANCEL, P-SWEEP-CONFIRMED, P-MONITOR (M0 foundation) |
| **6** | Launch gate | **PENDING** | Full DISPATCH_FLOW concurrent test suite green |
| **7** | Observability & ops notifications | **PENDING** | **Last** — after Flutter + admin UX freeze; see `OBSERVABILITY.md` exit gate |

**Phase 7 policy:** Do not start `M1+` tasks until Flutter apps + `ADMIN.md` exit gate are complete.
M0 (`P-MONITOR`) shipped in Phase 5. **While building Flutter apps:** maintain
[`OBSERVABILITY_GAPS.md`](./OBSERVABILITY_GAPS.md) (living gap register).

---

## Panchangam integration dashboard (§23.6)

Snapshot handoff: [`PANCHANGAM_STATUS_SNAPSHOT.md`](./PANCHANGAM_STATUS_SNAPSHOT.md) · Ops: [`PANCHANGAM_OPS.md`](./PANCHANGAM_OPS.md). **When any row below changes status, update the snapshot in the same change** (see snapshot §When to update).

| Track | Phase / task | Status | Next |
|-------|----------------|--------|------|
| Backend API + cache | `P-PANCHANGAM-API` … `ACCURACY` | **COMPLETED** | — |
| Prod separate node | `P-PANCHANGAM-DEPLOY` | **PENDING** | EC2/Docker private URL runbook |
| Ops launch gate | `P-PANCHANGAM-LAUNCH-GATE` | **PENDING** | Venkatrama sign-off checklist |
| Customer home ribbon | `C-PANCHANGAM-UI` | **IN_PROGRESS** | `C-FLUTTER-PANCHANGAM` — ribbon QA vs design 01 |
| Customer catalogue UI | `C-FLUTTER-CATALOG` | **COMPLETED** | Home + full list + detail on device (2026-08-05); `CATALOG_SYNC.md` |
| Customer full calendar | `C-PANCHANGAM-CALENDAR` | **PENDING** | Post-launch; month API + wider cache |
| Partner app | — | **N/A** | No panchangam/calendar in partner scope |

**Active mobile focus:** `C-FLUTTER-CUSTOMER` (catalogue + checkout waves) and `P-FLUTTER-PARTNER` polish (HOLD bucket).

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
| P-DISPATCH-SUPPLY | COMPLETED | `assert_dispatch_supply()` — 422 `NO_DISPATCH_SUPPLY` at `POST /bookings`; catalog filters pujas without verified pricing; `scripts/sync_active_puja_pricing.py`; `tests/test_dispatch_supply.py` + `tests/test_wave1_dispatch_e2e.py` |

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
| P-SWEEP | COMPLETED | — | 5-step sweep + rebroadcast enqueue; **2026-08-02:** step-4 stranded scan fixed — see `P-SWEEP-ZERO-OFFER-RETRY` |
| P-SWEEP-ZERO-OFFER-RETRY | COMPLETED | — | DISPATCH_FLOW §4 alignment: `bookings_needing_rebroadcast` uses `last_dispatched` (not assignment history); `bookings_needing_initial_broadcast` for lost first `broadcast_booking`; `dispatch_round_done` logs `candidates`/`live`; `tests/test_sweep.py` (5 tests) |
| P-REFUND | COMPLETED | — | refund worker (live Razorpay TBD) |
| P-AUTH | COMPLETED | 2 | `otp/request` → `sms_router`; `sms_sent` + `sms_provider` in response |
| P-SMS-ROUTER | COMPLETED | 2 | FAST2SMS primary, MSG91 held (`MSG91_ENABLED=false`); `test_sms_router.py` |
| P-WS | IN_PROGRESS | 2 | `booking_events` publishes on confirm + accept; location events TODO |
| P-NOTIFY | COMPLETED | 2 | FCM + SMS fallback worker; `notifications` queue; **2026-08-02:** see `P-FCM-ANDROID-CHANNEL` |
| P-FCM-ANDROID-CHANNEL | COMPLETED | 2 | `fcm_client.py` — high-priority pushes set `android.notification.channel_id=mana_guruji_offers_high` + `sound=default`; legacy API `android_channel_id`; `tests/test_phase2_clients.py::TestFcmClient` |
| P-CANCEL-OFFERS-SYNC | COMPLETED | — | Customer cancel expires pending assignments (`expired` + `responded_at`); `GET /v1/offers` filters `cancelled_at IS NULL`; `test_launch_slice.py` |
| P-FCM-CUSTOMER-CANCEL | IN_PROGRESS | 2 | Partner FCM when customer cancels — `data.type=offer_withdrawn`; enqueue from `cancellation_service`; partner handler + dismiss modal. Poll + 410 refresh are safety nets (`P-CANCEL-OFFERS-SYNC`) |
| P-TXN-LOCK | COMPLETED | — | re-audit: `pujari_tax_year.gross_facilitated` under same guarded UPDATE |
| P-REFUND-CAP | COMPLETED | 3 | `trg_refunds_cap_total` vs `payments.amount` (mig 005 verified) |
| P-AUTH-FIX | COMPLETED | 4-0 | jti lookup + `verify_secret`; reuse-detection revokes all; Redis OTP lockout; `test_sprint40_auth.py` |
| P-ADMIN-AUTH-FIX | COMPLETED | 4-0 | `app_context` body `Literal["customer","pujari"]` — admin impossible on SMS path |
| P-ADMIN-ROLE | COMPLETED | 4-0 | `get_principal` loads `user_roles` (admin ctx only), 403 on revoke-after-issue; `require_roles`/`require_admin_role`; issuance gated to TOTP login; `test_sprint40_admin.py` |
| P-ADMIN-SEED | COMPLETED | 4-0 | roles seeded (mig 009); `scripts/bootstrap_admin.py` (env-keyed first admin); `POST/DELETE/GET /v1/admin/users/{id}/roles` (last-admin guard); all audited |
| P-ADMIN-AUTH | COMPLETED | 4-0 | TOTP login `POST /v1/admin/auth/login` (stdlib RFC 6238), admin-vouched provisioning `POST /v1/admin/users/{id}/credential`, Fernet-encrypted secrets, replay guard, per-context short TTL; live-smoke + unit tests green |
| P-EXC-ADMIN-PATHS | COMPLETED | 4C | Admin 409 vs webhook 200 for refund overlap + reassign copy |
| P-PGBOUNCER | PENDING | — | prepare_threshold=None |
| P-MONITOR | COMPLETED | 5 | M0 foundation — `app/monitoring/`; Phase 7 extends via `M-*` tasks |
| P-GST-MODEL | BLOCKED | 3 | blocked_by: CA memo → `advisor_signoff_ref` |
| P-SPLIT-CONFIG | PENDING | 3 | `tax_*_config` tables — schema unblocked; seed needs memo |
| P-SPLITS | PENDING | 3 | reads snapshotted config on booking |
| P-TDS-393 | PENDING | 3 | **P0** — s.393 withholding; not gated on GST memo |
| P-IGST | PENDING | 3 | blocked_by: `billing_state_code` (C-ADDR) |
| P-INVOICE-SERIES | PENDING | 3 | scope gated on Q16; SAC code required |
| P-RAZORPAY-ROUTE | PENDING | 3 | **P0** — confirm Route before taking money (RBI) |
| P-PAN-STATUS | PENDING | 3 | TRACES operative check + re-check job |
| P-197-ASSIST | PENDING | 5 | Form 13 nil-deduction; PAN prerequisite now |
| P-PAYOUT | PENDING | 3 | blocked_by: P-SPLITS, P-RAZORPAY-ROUTE |
| P-SWEEP-CONFIRMED | COMPLETED | 5 | stuck confirmed / no-show — alert-only sweep (`booking_no_show_alerts`, mig 015); admin resolves manually |
| P-RECONFIRM | COMPLETED | Launch §21.7 — sweep + notify (advance ≥24h lead) |
| P-APP-CONFIG | COMPLETED | — | §23 — `GET /v1/app-config` public read (`night_bookings_enabled`, `instant_lead_hours`, `advance_booking_amount`) |
| P-RECONFIRM-API | COMPLETED | — | §23 — `POST /v1/pujari/bookings/{id}/reconfirm` → `pujari_confirmed_at` |
| P-FLUTTER-CONTRACT | COMPLETED | — | §23 — `booking_class` on C-GET/list + create response; `is_muhurat_bound` on catalog |
| P-PANCHANGAM-API | COMPLETED | — | §23 — endpoint + schema shell; `GET /v1/panchangam` reads `panchangam_daily` |
| P-PANCHANGAM-FIELDS | COMPLETED | — | §23.6 — `vaaram`, `yama_gandam`, `sunrise`, `sunset`; telugu-panchangam-app vendor normalizer |
| P-PANCHANGAM-VENDOR | COMPLETED | Launch | §23.6.1 — `panchangam_cities.py` + lat/lng/tz vendor fetch + strict upsert + 7-day cache + beat lock |
| P-PANCHANGAM-ACCURACY | COMPLETED | Launch | §23.6.1 — `panchangam_reference_hyderabad.csv` + `validate_panchangam_accuracy.py` + CI fixtures |
| P-PANCHANGAM-DEPLOY | PENDING | Launch | §23.6.1 — dev same-host engine; prod separate EC2/Docker private URL |
| P-PANCHANGAM-LAUNCH-GATE | PENDING | Launch | `PANCHANGAM_OPS.md` sign-off checklist before release |
| P-OPENAPI-ARTIFACT | COMPLETED | — | §23 — commit `spec/openapi.json` for Flutter codegen |
| P-PLL-GEOM | PENDING | — | migration **008** (007 is tax migration) |

---

## Customer

| ID | Status | Phase | Notes |
|---|---|---|---|
| C-QUOTE | IN_PROGRESS | 3 | re-open: fee fields + tax config snapshot on quote |
| C-HOLD | IN_PROGRESS | 3 | re-open: carries snapshot (`tax_*_config_id`, `total_charged_online`) |
| C-BOOK | IN_PROGRESS | 3 | re-open: inherits from hold; never re-reads current config |
| C-CANCEL | COMPLETED | — | customer cancel; pending assignments expired in same txn (`P-CANCEL-OFFERS-SYNC`) |
| C-PUJAS | COMPLETED | 4B | Wave 4: `GET /v1/pujas` (price_from/to, hero, categories) + `GET /v1/pujas/{id}` (content, addons, gallery) |
| C-PUJARIS | COMPLETED | 4B | Wave 4: `unit_price` via `pricing_resolver`; verified + availability filters |
| C-GET | COMPLETED | 1 | full detail: pujari, history, refund, address |
| C-DISPATCH-CHOICE | SKIPPED | Launch §21 — direct disabled; endpoint reserved Phase 2 |
| C-WS | IN_PROGRESS | 2 | receives `status_changed` via Redis pub/sub; location events TODO |
| C-LIST | COMPLETED | 1 | `GET /v1/bookings` keyset (created_at, id) |
| C-ADDR | IN_PROGRESS | 3 | re-open: `billing_state_code` + **`service_area_id`** (§21) — **area required on create/update** |
| C-PROMO | COMPLETED | 1 | atomic counter upsert + redemption in checkout txn |
| C-PAGINATION | COMPLETED | 1 | encode/decode_cursor in schemas/common.py |
| C-DEVICE | COMPLETED | 2 | shared `devices.py` with pujari |
| C-PANCHANGAM-UI | IN_PROGRESS | Launch | Ribbon scaffold exists (`customer_home_screen`, `panchangam_ribbon`). **Active:** Wave 1 API gate (`seed_panchangam` + `GET /v1/panchangam`) then design alignment + device QA (`locale=te`/`en`, 404 retry, Drik label). Backend (`P-PANCHANGAM-*` through ACCURACY) done. |
| C-PANCHANGAM-CALENDAR | PENDING | 2 | Full calendar tab (design screen 04); needs month API + wider cache + auspicious rule |

---

## Partner (pujari)

| ID | Status | Phase | Notes |
|---|---|---|---|
| B-OFFERS | COMPLETED | — | GET offers — excludes `cancelled_at`; see `P-CANCEL-OFFERS-SYNC` |
| B-ACCEPT | COMPLETED | — | accept race |
| B-HEARTBEAT | COMPLETED | Launch §21 — presence without required GPS |
| B-BOOKINGS | COMPLETED | `GET /pujari/bookings` list + `GET /pujari/bookings/{id}` detail |
| B-START | COMPLETED | — | start service |
| B-BALANCE | COMPLETED | — | balance collected ack |
| B-COMPLETE | COMPLETED | — | complete service |
| B-REJECT | COMPLETED | reject + P-REJECT-FAST celery enqueue |
| B-EARNINGS | PENDING | 3 | blocked_by: P-SPLITS; + TDS line, ₹4.5L nudge |
| B-AVAIL | COMPLETED | 1 | `PUT/GET /v1/me/availability` replace-all |
| B-UNAVAIL | COMPLETED | 1 | `PUT/GET /v1/me/unavailability` replace-all |
| B-KYC | HOLD | 0.5 | DigiLocker Aadhaar + **nullable PAN pull** — **deferred** (eKYC vendor discussions in progress) |
| B-DEVICE | COMPLETED | 2 | `POST/DELETE /v1/me/devices`; upsert by `device_token` |
| B-CANCEL | COMPLETED | 5 | `POST /v1/bookings/{id}/pujari-cancel` → requested + `rebroadcast(fresh=True)`; `test_pujari_cancel.py` |
| B-REGISTER | HOLD | profile bootstrap — **deferred** (eKYC vendor discussions in progress) |

---

## Admin

| ID | Status | Phase | Notes |
|---|---|---|---|
| P-ADMIN-AUTH-FIX | COMPLETED | 4-0 | `app_context` in body; query-param escalation closed |
| P-AUTH-FIX | COMPLETED | 4-0 | refresh/logout jti; Redis OTP lockout; reuse detection |
| P-ADMIN-ROLE | COMPLETED | 4-0 | `get_principal` loads roles (admin ctx only); issuance gated to TOTP login; `require_admin_role` |
| P-ADMIN-SEED | COMPLETED | 4-0 | `bootstrap_admin.py` + roles endpoints (assign/revoke/list, last-admin guard) |
| P-ADMIN-AUTH | COMPLETED | 4-0 | TOTP login + admin-vouched provisioning; Fernet secrets; replay guard; short per-context TTL |
| P-EXC-ADMIN-PATHS | COMPLETED | 4C | admin vs webhook HTTP mapping in `exceptions.py` |
| A-ADVANCE | COMPLETED | — | advance booking amount (now audited) |
| A-AUDIT-LOG | COMPLETED | 4A/4C | mig 009 + `audit.py`; mutation rows on advance, roles, credential; **4C tail:** `action=read` on `A-SEARCH` + `A-BOOKING-DETAIL` + booking money reads |
| A-SEARCH | COMPLETED | 4C | `GET /admin/bookings` — phone/id/status/date + PII read audit |
| A-BOOKING-DETAIL | COMPLETED | 4C | `GET /admin/bookings/{id}` — 360° ops view |
| A-ADMIN-UI | COMPLETED | 4A | `admin_ui/` Next.js 15 shell — TOTP login, role-gated nav (`GET /admin/me`), advance/roles/credential screens; CORS `localhost` + `127.0.0.1`; TanStack Query + Zod |
| A-CAT-CATEGORIES | COMPLETED | 4B | `GET/POST/PUT /v1/admin/catalog/categories` + `PATCH .../categories/reorder`; slug/order/description; `catalog_admin.py`; `test_sprint4b_catalog.py` + `test_admin_catalog.py` |
| A-CAT-PUJAS | COMPLETED | 4B | `GET/POST/PUT /v1/admin/catalog/pujas` + `GET .../impact` + `PATCH .../reorder`; price_max guard; audit |
| A-CAT-ADDONS | COMPLETED | 4B | `GET/POST /pujas/{id}/addons` + `PUT /addons/{id}` |
| A-CAT-CONTENT | COMPLETED | 4B | `GET/PUT /pujas/{id}/content` — replace-all per `kind` |
| A-CAT-MEDIA | COMPLETED | 4B | `POST /media/presign` + `PUT .../upload` (proxy) + `POST .../confirm` + `GET /media`; `catalog_media.py` |
| A-CAT-UI | COMPLETED | 4B | `admin_ui` catalogue builder — `/console/catalog`, `/console/catalog/pujas/[id]` |
| C-CAT-READ | COMPLETED | 4B | Wave 4 customer read — `catalog_read.py`, `catalog_customer.py` schemas |
| A-PUJARI-PRICING | COMPLETED | 4B | `GET/PUT /v1/admin/pujaris/{id}/pricing` + Partners UI; replace-all matrix; audited |
| A-PUJARI-SEARCH | COMPLETED | 4B | `GET /v1/admin/pujaris` — phone/name/verification/area search + cursor |
| A-AREAS | COMPLETED | 4B | `GET/POST/PUT /v1/admin/service-areas` + deactivation guard; `PUT /v1/admin/pujaris/{id}/service-areas`; admin UI `/console/settings/areas` |
| A-RM | COMPLETED | 4B | `GET/POST/PUT /v1/admin/relationship-managers` + default setting; assign on accept; admin UI |
| A-KYC | COMPLETED | 4B | `GET /v1/admin/kyc/pending`, `POST .../approve|reject`, `GET .../pujaris/{id}`; doc-level review; pujari verified when required set complete; admin-only writes; KYC queue UI |
| A-REASSIGN | COMPLETED | 4C | `POST /v1/admin/bookings/{id}/reassign` — clear-revoke-insert; mig 009 `revoked` ✅ |
| A-REFUND | COMPLETED | 4C | `POST /v1/admin/refunds/override` + `GET ?status=failed_permanent`; support caps via `platform_settings` |
| A-PROMO | COMPLETED | 4C | `GET/POST/PUT /admin/promos` — CRUD + date validation (schema + DB CHECK); admin UI `/console/promos` |
| A-DISPUTE | COMPLETED | 4C | `POST /admin/bookings/{id}/dispute` — `in_progress` → `disputed`; offline balance note; booking detail UI |
| A-MONEY-READ | COMPLETED | 4C | `GET /admin/bookings/{id}/money` — read-only; label "Collected online — settlement pending" |

---

## Phase 2 — Notifications (Sprint 2)

### Done (backend code + unit tests)

| ID | Status | Notes |
|---|---|---|
| P-SMS-ROUTER | COMPLETED | `sms_router.py`, `fast2sms_client.py`, `msg91_client.py`; SPEC_AMENDMENTS §17 |
| P-AUTH | COMPLETED | OTP via router; `sms_sent` + `sms_provider`; DEBUG `otp_dev_only` when all providers fail |
| P-NOTIFY | COMPLETED | `notify_offers`, `notify_no_pujari`; FCM 3× retry; UNREGISTERED → delete device |
| P-FCM-ANDROID-CHANNEL | COMPLETED | Android tray sound channel — `fcm_client.py` + partner `MainActivity` `mana_guruji_offers_high` |
| B-DEVICE | COMPLETED | `devices.py` — `POST/DELETE /v1/me/devices` |
| C-DEVICE | COMPLETED | Same `devices.py` for customer tokens |
| P-WS | IN_PROGRESS | `booking_events.py` on payment confirm + offer accept; **location events TODO** |

### Pending (external dependencies — not backend bugs)

| ID | Status | Notes |
|---|---|---|
| P-SMS-DLT | BLOCKED | Live SMS delivery — **DLT registration mandatory even for vendor testing** (TRAI). Provider may accept API calls but reject/drop messages without registered entity, header, and template. Use `DEBUG=true` + `otp_dev_only` until DLT approved. See SPEC_AMENDMENTS §18. |
| P-FCM-E2E | IN_PROGRESS | Partner handlers + channel shipped (2026-08-09). **Remaining:** device sign-off `test/PARTNER_FCM_SOUND.md` C1–C4; **`P-FCM-CUSTOMER-CANCEL`**; customer flavor not started |
| Phase 2 exit gate | PENDING | Met when P-WS location events done **and** P-SMS-DLT unblocked **and** `P-FCM-E2E` **COMPLETED** (partner sound QA + **`P-FCM-CUSTOMER-CANCEL`** + customer push) |

---

## Phase 4 — Admin control plane (Sprint 4)

| Sprint | Status | Notes |
|---|---|---|
| 4-0 hotfix | **COMPLETED** | Migration 009 applied. `P-ADMIN-AUTH-FIX`, `P-AUTH-FIX`, `P-ADMIN-ROLE`, `P-ADMIN-SEED`, `P-ADMIN-AUTH` — tests + live smoke green |
| 4A | **COMPLETED** *(core)* | **Shipped:** `admin_ui/` shell, `GET /v1/admin/me`, CORS, mutation audit on live admin endpoints. **Tail closed in 4C slice 2:** support refund-cap (`A-REFUND`), PII-read audit (`A-SEARCH`) |
| 4B | **COMPLETED** *(backend)* | §21 launch APIs + catalogue/KYC/pricing/areas/RM/reconfirm — **this repo**. Flutter partner: see **Mobile apps** (`P-FLUTTER-PARTNER` IN_PROGRESS) |
| 4C | **COMPLETED** | Slices 1–3 DONE + **manual QA sign-off 2026-07-22**: search, detail, reassign, refund override, promos, dispute, money read; `test_admin_slice3.py` (6 tests green) |

See `ADMIN.md` exit gate. **Phase 4 ≠ go-live.**

---

## Phase 6 — Launch gate (full suite)

| Test | Status | Notes |
|---|---|---|
| LG-double-accept | PENDING | concurrent double-accept |
| LG-webhook-same-window | PENDING | concurrent webhook |
| LG-webhook-vs-sweep | PENDING | both orderings |
| LG-cross-mode-overlap | PENDING | direct + broadcast overlap |
| LG-rebroadcast-idempotent | PENDING | duplicate rebroadcast; partial coverage in `test_sweep.py` zero-offer retry (not full duplicate-delivery gate) |
| LG-refund-no-double | PENDING | refund retry safety |
| LG-manual-reassign | COMPLETED | `tests/test_admin_slice2.py::test_lg_manual_reassign` |
| LG-sibling-supersede | COMPLETED | `tests/test_migration_014.py::test_sibling_supersede_on_first_accept` |
| LG-refresh-vs-accept | COMPLETED | `tests/test_advance_ttl.py::test_lg_refresh_vs_accept_no_phantom_live_offer` |
| LG-urgency-flip-idempotent | COMPLETED | `tests/test_urgency_flip.py::test_lg_urgency_flip_idempotent` |
| LG-duration-overlap-accept | COMPLETED | `tests/test_duration_ci.py::test_lg_duration_overlap_accept` (+ concurrent variant) |
| LG-night-gate | COMPLETED | `tests/test_booking_gate.py` — night slot → 422 before Razorpay |

See DISPATCH_FLOW.md §Test evidence (v2 launch gate).

---

## Phase 7 — Observability (post-app-design, **last**)

Policy: [`spec/OBSERVABILITY.md`](../OBSERVABILITY.md). Tasks: [`OBSERVABILITY.md`](./OBSERVABILITY.md).

**Gate (all must be true before M1+):** Flutter customer + partner feature-complete; `ADMIN.md` exit
gate signed off; booking lifecycle API frozen.

### M0 — Stuck-state foundation (shipped Phase 5)

| ID | Status | Notes |
|---|---|---|
| P-MONITOR | COMPLETED | `app/monitoring/` — see Phase 5 platform row |
| P-SWEEP-CONFIRMED | COMPLETED | Alert-only no-show |

### M1 — Lifecycle instrumentation

| ID | Status | Notes |
|---|---|---|
| M-LIFECYCLE-EVENTS | PENDING | 7 | `booking_lifecycle` logs + `puja_booking_lifecycle_events_total` on every DISPATCH_FLOW step |
| M-LIFECYCLE-WS | PENDING | 7 | WS `status_changed` parity with lifecycle steps; blocked_by: M-LIFECYCLE-EVENTS |

### M2 — Ops notifications (admin / RM attention)

| ID | Status | Notes |
|---|---|---|
| M-BOOKING-NOTIFY | PENDING | 7 | Admin in-app notification on new paid booking (`requested`) |
| M-BOOKING-NOTIFY-CONFIRMED | PENDING | 7 | Admin + RM on `confirmed`; blocked_by: M-BOOKING-NOTIFY |
| M-OPS-NOTIFY-MATRIX | PENDING | 7 | Upgrade refund/dispatch/no-show to admin notify + optional Slack |
| M-KYC-NOTIFY | PENDING | 7 | KYC backlog digest; blocked_by: A-KYC |

### M3 — Component health metrics

| ID | Status | Notes |
|---|---|---|
| M-HEALTH-DB | PENDING | 7 | Connection pool gauges |
| M-HEALTH-REDIS | PENDING | 7 | Redis latency / ping |
| M-HEALTH-CELERY | PENDING | 7 | Queue depth + task failures |
| M-HEALTH-SMS | PENDING | 7 | Provider send/fail counters |
| M-HEALTH-FCM | PENDING | 7 | Push send/fail counters; blocked_by: `P-FCM-E2E` + `P-FCM-CUSTOMER-CANCEL` (IN_PROGRESS) |
| M-HEALTH-PAYMENT | PENDING | 7 | Webhook + capture SLIs |
| M-HEALTH-KYC | PENDING | 7 | Pending documents gauge |
| M-HEALTH-BOOKING | PENDING | 7 | Time-in-status SLIs; blocked_by: M-LIFECYCLE-EVENTS |

### M4 — Dashboards & runbooks

| ID | Status | Notes |
|---|---|---|
| M-GRAFANA-DASHBOARDS | PENDING | 7 | Platform + booking + payment + refund dashboards |
| M-GRAFANA-ALERTS | PENDING | 7 | Alert rules + routing (PagerDuty / Slack) |
| M-RUNBOOKS | PENDING | 7 | Per alert_type ops runbooks |

### M5 — Synthetic probe

| ID | Status | Notes |
|---|---|---|
| M-SYNTHETIC-PROBE | PENDING | 7 | E2E canary + `puja_synthetic_probe_success`; pre-prod go-live gate |

### M6 — Tracing (optional)

| ID | Status | Notes |
|---|---|---|
| M-OTEL-TRACES | PENDING | 7 | OpenTelemetry; P2 — SKIPPABLE at exit gate |

---

## How to update (workflow)

1. Pick task from track file → set its status **in this file** to **IN_PROGRESS** when you start.
2. Implement → run acceptance from track file + relevant tests.
3. Set **COMPLETED** (or **SKIPPED** with reason) **in this file** in the same PR/commit.
   Never add a `Status:` line to a track file.
4. Re-check **Phase dashboard** — flip phase to IN_PROGRESS/COMPLETED as appropriate.
5. Run `pytest tests/ -q` and note count in the header line above.
