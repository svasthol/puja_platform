# TDS Launch Status — Sprint 2 (s.393, ex-194-O)

> **This document is complete; the TDS feature it describes is not launch-ready.** Gate = §0.
> At MVP launch TDS is **off** (`TDS_ACCRUAL_ENABLED=false`) — nothing is accrued, withheld, or
> deposited. That is a **known, owner-accepted exposure** pending CA guidance (§0.C, memo
> Q-recovery), **not** a settled-compliant design. A correct accrual pipeline (shadow, still no
> withholding) is milestone §0.S; actual deduction/deposit is Phase 3 (`P-TDS-393`, §0.P3).

> **Code review playbook:** [`TDS_CODE_REVIEW.md`](./TDS_CODE_REVIEW.md) · dated runs: [`plans/reviews/`](./reviews/)  
> **Accrual policy (CA v2/v3):** [`TDS_ACCRUAL_POLICY.md`](./TDS_ACCRUAL_POLICY.md) · **v3 engine:** [`TDS_V3_IMPLEMENTATION.md`](./TDS_V3_IMPLEMENTATION.md)  
> **Readiness / staging gates:** [`TDS_READINESS.md`](./TDS_READINESS.md) · [`TDS_STAGING_ROLLOUT.md`](./TDS_STAGING_ROLLOUT.md) · **Ops:** [`TDS_PRODUCTION_OPS_READINESS.md`](./TDS_PRODUCTION_OPS_READINESS.md)

**Authority:** On any conflict, [`STATUS.md`](./STATUS.md) wins for task status; this doc owns the
launch narrative and exit gate. Normative tax spec: [`SPEC_AMENDMENTS.md §16`](./SPEC_AMENDMENTS.md),
[`A-TAX-CONFIG.md`](./A-TAX-CONFIG.md). Written from code (`app/services/tds_accrual_service.py`,
`app/services/pricing.py`, `app/api/v1/endpoints/service_lifecycle.py`, `app/services/admin_dispute.py`,
`spec/db/migration_025.sql`, `app/core/config.py`) as of 2026-09-14.

---

## Launch posture — OFF (not shadow)

At MVP launch TDS does not operate (`TDS_ACCRUAL_ENABLED=false`). The decouple pipeline (§0.S
S1–S13) is **shipped in code** (migration 027, Celery worker, admin reconcile/correction); **shadow
is not flipped in production** until staging QA (S14). Do not enable accrual on the pre-027 inline
path — that ledger is invalid. Off remains the production posture until owners accept §0.C and S14
passes.

| Milestone | Posture | Meaning |
|-----------|---------|---------|
| **§0.L** — MVP launch | TDS **off** | Marketplace launches; TDS does not operate. Minimal gates below. |
| **§0.S** — Shadow on | Accrue, withhold nothing | Decouple **code shipped**; flip flag on staging/prod only after S14; withhold nothing until §0.P3. |
| **§0.P3** — Deduction/deposit | Withhold + deposit | Phase 3 (`P-TDS-393`): TAN, deposit, recovery mechanism, CA sign-off, `pan_enc` filing, `catch_up`. |

---

## §0 Exit gate

### §0.L — MVP launch (TDS OFF)

| # | Gate | State |
|---|------|-------|
| L1 | `TDS_ACCRUAL_ENABLED=false`; record-balance + complete flows unaffected (no 422, no wedged bookings) | ✅ (flag default false) |
| L2 | This doc's first line = not launch-ready + OFF posture | ✅ |
| L3 | Readiness script (no PII): v3 exposure (over ₹5L without operative PAN), pending recovery sum, **ledger TDS net** (`accrual+catch_up − reversal`) vs `tds_accrued` per FY row; `--strict` for staging | ✅ (`check_tds_readiness.py`, [`TDS_READINESS.md`](./TDS_READINESS.md)) |
| L4 | Point-in-time `entity_type` + raw PAN-presence captured at balance collection even while OFF (`CLASSIFICATION-CAPTURE`, migration 026, fail-open write) | ✅ (`tds_snapshot_*` on `confirm-balance-collected`) |
| L5 | §0.C s.201 risk acceptance signed by named owner, with real `G` number | ☐ |
| L6 | PAN-drive, TAN, CA-memo-sender owners named; memo sent | ☐ |

### §0.S — Shadow on (decouple PR; correct pipeline, nothing withheld)

| # | Gate |
|---|------|
| S1 | Decouple + intent migration; worker constraints 1–5 (D3) | ✅ migration 027 + `app.workers.tds_accrual` |
| S2 | Reversal integrity: unconditional (R1) + one reversal/booking (R2) + offline-keyed (R6) | ✅ |
| S3 | Ordered per-pujari processing (R4) | ✅ `process_pending_accrual_intents` |
| S4 | Parked-intent mechanism (R13) + bounded backlog (`ADMIN-COMPLIANCE`) | ✅ `GET /v1/admin/tds/compliance-backlog` |
| S5 | Partial ack cannot complete silently (D2) | ✅ `complete` requires full `balance_collected_amount` |
| S6 | BASE-COMPOSITION: accrue on `total_amount` (R7) | ✅ enqueue uses `total_amount` |
| S7 | FY reconciliation green | ✅ admin + script; **verify green in staging after shadow** |
| S8 | Per-pujari readiness auditable (R13) | ✅ readiness rows on compliance-backlog |
| S9 | Correction operator path (D4) | ✅ `POST .../correct-offline-collection` |
| S10 | FY hot-row `FOR UPDATE` removed on read paths (R3) | ✅ `_read_fy_row` on snapshot reads |
| S11 | Six statutory fields in `tax_statutory_config` (R9) | ✅ |
| S12 | Operative-PAN fail-safe (R10) + FY gate aligned | ✅ `pan_status` + `use_no_pan_tds_rate`; **Sep 2026:** `PUJARI_FY_PAN_GATE` block uses **`pan_status=operative`** |
| S13 | FY-boundary single IST clock (R14) | ✅ `collected_at` from balance collection |
| S14 | Flip `TDS_ACCRUAL_ENABLED=true` (shadow/platform-bears) only after S1–S13 | ☐ staging QA + `--strict` + **`export_tds_26q.py`** spot-check + dated code review |

### §0.P3 — Deduction / deposit (Phase 3, `P-TDS-393`)

| # | Gate |
|---|------|
| P3-1 | CA sign-off on s.393 deduction/deposit/recovery model (memo sent in launch prep) |
| P3-2 | TAN obtained (acquisition starts in launch prep — longest lead time) |
| P3-3 | Deposit pipeline + funding model; deposit by **7th of next month** (30 Apr for March) |
| P3-4 | Recovery mechanism — platform never held offline funds (Q-recovery answered) |
| P3-5 | `pan_enc` populated + decryptable (R8); bulk PAN-operative verification (Protean/NSDL) at KYC |
| P3-6 | Q1b retroactivity + `catch_up` over OFF/shadow window + TCS §52 items |
| P3-7 | Operative-PAN deposit impact (R10) |
| P3-8 | Actual withholding from payouts live; **26Q quarterly + Form 16A + TRACES** filing; verification block pasted |

**A — Direction is spec-set** (§16): full puja value; CA confirms `booking_fee` Razorpay + partial-collection edge cases only.

---

## Product & ops (§0.L companion — not withholding)

Shipped so marketplace UX matches launch TDS posture (OFF accrual; honest money copy; PAN capture
without Phase 3 deposit). Task IDs in [`STATUS.md`](./STATUS.md).

| Area | Delivered | Notes |
|------|-----------|--------|
| Customer billing clarity | `C-FLUTTER-BILLING-BREAKDOWN` | Checkout + booking detail: puja to pujari, platform fee online, total customer pays |
| Partner billing clarity | `P-FLUTTER-BILLING-BREAKDOWN` | Booking detail mirrors breakdown + `booking_fee` / label from API |
| Partner FY / TDS read-only | `P-FLUTTER-TAX-SUMMARY` | `GET /me/tax-summary`; informational while TDS OFF / shadow |
| PAN + entity profile | `P-FLUTTER-PAN-PROFILE`, `L-SPRINT-2-TDS-PAN-PROFILE` | `POST /kyc/pan`, `GET/PUT /me/tax-profile`; optional accept gates via `PAN_ACCEPT_GATE_ENABLED`, `PUJARI_TAX_PROFILE_REQUIRED_FOR_ACCEPT`, **`PUJARI_FY_PAN_GATE_ENABLED`** (`PAN_FY_GATES.md`) |
| Admin booking ops | `L-SPRINT-2-TDS-ADMIN-OPS-UX` | `GET /admin/bookings?booking_class=` tabs; instant vs advance queues |
| Admin FY pujari earnings | same | `GET /admin/pujaris/fy-earnings` + admin UI (ops recon before shadow) |

Setu PAN **verification** shipped in `setu_digilocker_client.verify_pan` — enable via **`KYC_SETU_PAN_PRODUCT_ID`** (sandbox test PAN `ABCDE1234A` per Setu docs). `pan_enc` filing remains Phase 3.

---

## §0.C — Risk acceptance (launch precedes full memo answer)

> **Policy v3 (TDS engine):** Normative accrual + exposure model is [`TDS_ACCRUAL_POLICY.md`](./TDS_ACCRUAL_POLICY.md) + [`TDS_V3_IMPLEMENTATION.md`](./TDS_V3_IMPLEMENTATION.md). **Sign §0.C on v3 numbers**, not v13 “5%×all GMV”.

The memo is sent during launch prep; answers take weeks.

| Field | Content |
|-------|---------|
| **Decision** | Hyderabad MVP launches with TDS **off** before the CA memo returns. |
| **Exposure (principal, v3)** | **Individual/HUF:** **0%** TDS on FY facilitation **below ₹5L**; **0.1%** on the **slice above ₹5L** when PAN is **operative**; **5% fail-safe** on that slice when over ₹5L **without operative PAN** (not on all GMV from ₹1). **Always-taxed entities:** **0.1%** on puja value. |
| **Plus** | s.201(1A) interest **1%/month** on any shortfall if deduction/deposit later required; potential s.271C penalty. No s.40(a)(ia) disallowance (platform doesn't expense the puja value). |
| **Order of magnitude** | Owner models **`G`** = monthly facilitation GMV that **crosses or exceeds ₹5L** without operative PAN × **~5%** on the **above-threshold slice** (much smaller than v13 `0.05×0.95×G`). Illustrative only — fill real `G` and crossing share **`s`**. |
| **Primary mitigation** | DigiLocker/Setu **PAN verify** (`B-KYC`) — operative PAN unlocks ₹5L threshold + 0.1% rate on crossing slice. |
| **Monitor** | [`check_tds_readiness.py --strict`](./TDS_READINESS.md) — zero **TDS** FY/ledger drift; count over-₹5L without operative PAN; pending recovery sum. |
| **Escalation trigger** | Over-₹5L-no-operative-PAN count or pending recovery sum crosses **₹[OWNER-SET]** → accelerate PAN drive; staging: [`TDS_STAGING_ROLLOUT.md`](./TDS_STAGING_ROLLOUT.md). |
| **Remediation if adverse** | Enable accrual per rollout; `catch_up` from classification snapshot; deposit shortfall + interest; recover per CA **Q-recovery** (stub off blocked until signed). |
| **Owner** | **[OWNER: TBD — founder/finance]** signs, with real `G` / crossing share filled in. |

---

## §2 Tax basis (spec vs code)

| Source | Gross basis |
|--------|-------------|
| SPEC_AMENDMENTS §16 (Example B) | **Full puja value — both online and offline portions**; excludes platform `booking_fee` |
| Code today | `balance_collected_amount` (offline slice via `collected`) — misses the online advance under `advance_balance` |
| Launch (`booking_fee`, `FULL_ONLINE_ENABLED=false`) | Divergence inert **only when collection is full** (gate S5); partial ack under-accrues vs §16 |
| **Target rule (§0.S6)** | Accrue on **`total_amount`** (puja value), not `collected`; lands with the `FULL_ONLINE_ENABLED` flip |

Rate table (code, `pricing_tds_v3` / `pricing.py` — matches s.194-O post-Oct-2024):
- Individual/HUF → **0%** until FY facilitated gross **> ₹5,00,000**, then **0.1%** on the **taxable slice** (operative PAN).
- No / inoperative PAN while **deduction latched** above ₹5L → **5% fail-safe** on taxable slice (not below-threshold band).
- Firm/company/trust/AOP/other (`always_taxed_entity_types`) → **0.1%** on full booking value.

---

## §5 Reversal matrix (from code)

Rule (R6): reverse iff the **offline collection** is reversed — never on online `booking_fee` refunds
(different supply). Current wiring: `admin_dispute.py` reverses only on `dispute_type='offline_non_payment'`
with `balance_collected_at` set; `reverse_tds_*` is (incorrectly) gated by `TDS_ACCRUAL_ENABLED` (R1).

| Path | Offline collection reversed? | TDS reversal | Status |
|------|------------------------------|--------------|--------|
| Dispute `offline_non_payment`, balance collected | Yes | Reverse (contra) | Wired (but flag-gated — R1) |
| Dispute `service`, offline money kept by pujari | No | None | Correct |
| Dispute `service`, offline money returned | Yes | Reverse | **Gap** — not wired |
| Admin correction lowering `balance_collected_amount` | Partial | Adjust | **Gap** — correction ops (D4) |
| Customer/online `booking_fee` refund | No (online only) | **None** | Correct — must not reverse |
| Booking cancel after accrual (admin) | Depends | Reverse if offline reversed | `reverse_tds_on_cancel` (flag-gated — R1) |
| No-show / abandoned before collection | No accrual | None | N/A |
| Reassignment before collection | No accrual | None | N/A |

---

## §6 Live proof (staging)

Staging QA has produced exactly one accrual ledger row (flag on in staging only): pujari
`0827e851-b4b3-40fe-935d-4990f5ed9ba3`, booking `f95a920e-dbe4-413f-a6fd-2c44ff9de0ea`. Production
launches with the flag **off** — no ledger rows in production. Counts are auditable via
`scripts/check_tds_readiness.py`. **Disclaimer:** staging rows are not production TDS and carry no
deposit obligation.

---

## §7 Defect register (Rn = review findings, Dn = doc/pipeline defects)

**Engineering status:** Milestone **S** remediations below are **shipped** in repo (migrations 026–027, decouple worker, admin TDS APIs). Task-level status: [`STATUS.md`](./STATUS.md) `L-SPRINT-2-TDS-*`. Still open: **D5** (OpenAPI artifact), **R8** (P3), **L5/L6** human gates.

| ID | Item | Sev | Milestone | Remediation |
|----|------|-----|-----------|-------------|
| D1 | Inline accrual on the critical path (`confirm-balance-collected`) | P0 | S | Decouple: record collection fact; accrue via worker |
| D2 | Partial ack completes silently (`complete` only checks `balance_collected_at` set) | P0 | S | Require full-collection ack (or explicit partial-close) |
| D3 | Decouple + intent migration not shipped | P0 | S | Intent table + ordered per-pujari worker |
| R1 | Reversal gated by `TDS_ACCRUAL_ENABLED` → orphaned accruals on flag-off (filing-accuracy + threshold-math corruption) | P0 | S | Reversal unconditional on accrual-row presence; flag gates new accruals only |
| R4 | Parking breaks ordered threshold math (`fy_gross_before` is order-dependent) | P0 | S | Ordered per-pujari processing; parked intent blocks later ones |
| R6 | Reversal keyed to dispute enum, not offline-collection reversal | P0 | S | Trigger on offline-collection reversal (§5) |
| R5 | Shadow-vs-withhold framing | P0 (doc) | L | OFF posture + §0.C exposure acceptance |
| R7 | BASE-COMPOSITION vs §16 (inert unless partial ack / flag flip) | P1 | S | Accrue on `total_amount`; tie to `FULL_ONLINE_ENABLED` + D2 |
| R2 | Double-reversal race (no unique index on `entry_type='reversal'`) | P1 | S | Unique partial index `(booking_id) WHERE entry_type='reversal'`; idempotent IntegrityError; `FOR UPDATE` booking row |
| R3 | FY hot-row `FOR UPDATE` on read paths (`tds_snapshot_for_booking`) | P1 (perf) | S | Read paths use plain `SELECT`; split `_read_fy_row`/`_lock_fy_row` |
| R9 | Six statutory fields in admin-editable `platform_settings.tds_facilitation` | P1 | S | Move all to `tax_statutory_config` (`puja_migrate` only) |
| R10 | Operative-PAN gap (FY gate used hash-only) | P1 | S | **Closed Sep 2026 close-out:** gate uses `pan_status=operative`; accrual still uses `use_no_pan_tds_rate` |
| R8 | `pan_enc` unused → cannot file 26Q/Form 16A (plaintext PAN needed) | P1 | P3 | Populate encrypted PAN + hash at KYC (dedicated key, SPEC_AMENDMENTS §19 pattern) |
| R12 | Append-only ledger REVOKE skipped if `puja_app` created after migration (§19 ordering trap) | P1 | S | Grants in idempotent `scripts/apply_grants.sql` every deploy |
| R13 | Global flag is a cliff (422s ~139 pujaris) — operational + shadow-ledger completeness | P1 | S | Per-pujari readiness/parking; global flag = new-accrual stop only |
| D4 | Correction ops surface missing | P1 | S | Operator correction path |
| R11 | Readiness script prints `u.phone` (DPDP/PII) | P1 | L | Drop phone; `pujari_id[:8]` + counts only |
| R14 | FY-boundary tz skew (two clocks) | P2 | S | Single IST `balance_collected_at` into accrual |
| D5 | OpenAPI stale (TDS endpoints) | P2 | S | Regenerate `spec/openapi.json` |
| R15 | Statutory rates not as-of collection — `load_tds_facilitation_config` uses latest `effective_from` only, not `collected_at` | P1 | S | `as_of=collected_at` in `_execute_accrual` (worker + `accrue_tds_on_balance_collected` / catch_up); reversion tests worker + catch_up in `test_tds_accrual_decouple` |
| D6 | Worker batch = one DB txn over up to 50 pujaris × all intents; DB error aborts txn → later intents + `failed` bookkeeping roll back (no SAVEPOINT) | P0 | S | `begin_nested` per intent + `_DEFAULT_INTENTS_PER_PUJARI=25`; `test_worker_poison_intent_quarantined_later_intent_accrues` |

---

## §8 Drift register

**Resolved in Sprint 2 (2026-09)** — do not re-open as launch blockers: R7 BASE-COMPOSITION enqueue;
R9 statutory fields in `tax_statutory_config`; R10 `pan_status`; R12 grants in `apply_grants.sql`;
R13 decouple + compliance backlog; `API_CONTRACTS.md` TDS + tax-profile + admin fy-earnings;
`DATABASE.md` accrual tables (see migration 025–027).

| Item | Type |
|------|------|
| `MASTER.md` payment model vs `booking_fee` on quotes/checkout | Doc sync — mobile breakdown shipped; MASTER narrative may lag |
| `PLATFORM.md` Form 140/131 vs `P-TDS-393` (26Q / Form 16A) | Doc sync — `L-SPRINT-2-TDS-SPEC-DOCS` / PLATFORM acceptance |
| `spec/openapi.json` vs live admin TDS + tax routes | Doc sync — `L-SPRINT-2-TDS-OPENAPI` (D5) |
| `in_progress`-only balance gate vs `API_CONTRACTS.md` | Product decision |
| `B-EARNINGS` ₹4.5L nudge vs statutory ₹5L | **Resolved** — `PAN_FY_GATES.md` + `L-SPRINT-2-TDS-PAN-FY-GATES` (warn ₹4.5L, block ₹5L without PAN) |

---

## Real-world ECO TDS benchmark (s.194-O peers)

| Dimension | Peers (Amazon / Flipkart / Meesho / Urban Company) | This platform | Action |
|-----------|-----------------------------------------------------|---------------|--------|
| PAN at onboarding | **Hard gate** — no seller transacts without PAN | ≈139/144 no PAN; still transact offline | PAN drive + progressive `PAN_ACCEPT_GATE_ENABLED` |
| Who holds the money | Platform holds at settlement → nets TDS at source | Pujari collects offline cash; platform never holds | Q-recovery (memo) — the real anomaly |
| Direct-payment case | Rare; s.194-O(1) deeming covers it | The norm (offline) | Same deeming — exposure is real (§0.C) |
| Rate (post-Oct-2024) | 0.1%; 5% no/invalid PAN | Matches | CA confirms currency |
| Operative PAN | Bulk Protean/NSDL verification | presence-only | R10 |
| Deposit / filing | 7th monthly; 26Q quarterly; Form 16A; TRACES | Not built | §0.P3 |

**Two genuine divergences no serious ECO has:** (1) transacting **un-PANed supply** (the entire
§0.C exposure), and (2) the platform **never touching the money** (makes deduction-at-source
impossible → Q-recovery existential). Everything else matches peer practice.

---

## Not in scope (ON HOLD)

GST (`P-GST-MODEL`), TCS §52 (memo only), Phase-3 money (`P-SPLITS`/`P-PAYOUT`). This document does
not authorize any deduction, deposit, or flag flip.
