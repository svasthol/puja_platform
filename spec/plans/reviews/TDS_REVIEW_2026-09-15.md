# TDS review run — 2026-09-15

| Field | Value |
|-------|--------|
| Reviewer | Adversarial re-review (Cursor agent) per `TDS_CODE_REVIEW.md` |
| Scope | Sprint 2 backend accrual decouple, worker batch (D6), statutory as-of (R15), reversals, admin surface |
| Environment | Static audit + **§8 pytest** (2026-09-15 local); `check_tds_readiness.py` on dev DB; staging §11.1 SQL **not run** |

**Prior run:** [`TDS_REVIEW_2026-09-14.md`](./TDS_REVIEW_2026-09-14.md) (D6/R15 Fail). This run targets the post-fix codebase.

---

## Verification map results (P0 + map §4)

| ID | Pass/Fail | Evidence / falsifier |
|----|-----------|----------------------|
| D1 | **Pass** | `service_lifecycle.confirm_balance` calls `enqueue_tds_accrual_intent` only; no sync `accrue_*` on HTTP path |
| D2 | **Pass** (narrow) | `complete` rejects when `balance_collected_amount < offline_due`. **Residual:** partial `confirm-balance` still sets `balance_collected_at` and enqueues intent on `total_amount` before completion gate — monitor under R7 / full-collection policy |
| D3 | **Pass** | `pujari_tds_accrual_intents` + `process_tds_accrual_intents` worker shipped |
| D6 | **Pass** | `begin_nested` in `_run_intent_accrual_with_savepoint`; `_DEFAULT_INTENTS_PER_PUJARI=25`; failed bookkeeping outside nested scope. Reversion: `test_worker_poison_intent_quarantined_later_intent_accrues` |
| R1 | **Pass** | `reverse_tds_on_cancel` has no `_accrual_enabled()` gate; `test_reversal_unconditional_when_flag_off` |
| R4 | **Pass** (correctness) | Per-pujari `ORDER BY collected_at` + `FOR UPDATE` on intent rows; ordering test in decouple suite. **Ops:** outer `db.begin()` still spans up to 50 pujaris × 25 intents/tick — pool pressure remains (playbook §6.1) |
| R6 | **Pass** (static) | `admin_dispute` reverses only on `offline_non_payment` with collection recorded; `cancellation_service` / `admin_refund` do not call `reverse_tds_*`. Online `booking_fee` refund path has no TDS reversal wiring |
| R15 | **Pass** | `_execute_accrual` uses `load_tds_facilitation_config(..., as_of=collected_at)`; `pricing.py` `effective_from <= as_of_date`. Reversion: `test_accrual_uses_statutory_row_as_of_collected_at`, `test_catch_up_accrual_statutory_as_of_collected_at` |
| R3 | **Pass** | `_read_fy_row` plain SELECT; `_lock_fy_row` `FOR UPDATE`; `test_fy_read_paths_do_not_lock_tax_year` |
| R10 | **Decision** | Migration 027 backfill `pan_status='operative'` for all `pan_hash` — still needs §0.C owner sign-off (0.1% vs 5% model) |
| R8 | **N/A** | `pan_enc` unused by design (P3); no plaintext PAN observed in admin TDS routes |

**No new P0 Fail** vs 2026-09-14 on static analysis.

---

## §8 Test gate (2026-09-15 local)

| Command | Result |
|---------|--------|
| Playbook pytest bundle | **31 passed, 1 failed** — `test_tds_accrual.py::test_fy_tax_summary` (`fy_gross_facilitation` expects ledger-only `100000.00`; `pujari_fy_tax_summary` returns `max(ledger, booking_gross)` → `100800`/`126000` with dev seed data) |
| `scripts/check_tds_readiness.py` | **Ran** — 1 reconcile drift row (`cccccccc` FY); 6 pending+parked intents; exposure monitor OK |

**Venv:** `uv pip install -r requirements-dev.txt` failed (`.pyd` file lock); **`.venv\Scripts\python.exe -m pip install -r requirements-dev.txt`** succeeded.

**Recommendation:** Fix or isolate `test_fy_tax_summary` (not a D6/R15 reversion test); re-run §8 before S14 flip. P0 reversion tests in decouple module **passed**.

---

## §6 Failure modes / S14 checklist

| Check | Status |
|-------|--------|
| Dated review, no open P0 Fail (code) | **Yes** |
| Reversion tests present for D6 + R15 | **Yes** (decouple module) |
| Poison-pill quarantine proven in CI | **Pending** local/CI pytest |
| Backlog batch duration measured (§11.1) | **Not run** |
| Reconcile green on staging | **Not run** |
| Worker concurrency vs txn length documented | Unchanged — cap 50×25 intents/tick; long txn risk noted |

**S14 flip verdict:** **Do not flip** `TDS_ACCRUAL_ENABLED` in production until §11.1 staging counts + §8 pytest green + reconcile green on staging. Code-review P0 blockers from 2026-09-14 are **cleared** in tree.

---

## §0.C / §7 (unchanged)

- Readiness script: no-PAN exposure still uses `float` (`nopan_gross * 0.05`) — label **indicative** or move to `Decimal` before finance sign-off.
- R10 operative backfill: owner decision still required.

---

## Admin UI (§7)

- TDS settings page edits rates/thresholds only — no PAN plaintext in grep pass.
- Routes use `require_admin` / `require_admin_role`.

---

## Flutter (deferred)

- `mana_guruji_mobile/lib/features/partner/tds_accrual_info.dart` — no `double.parse` / `toDouble()` on tax-summary fields in partner TDS helper (spot check).

---

## STATUS linkage

- Closes gate for `L-SPRINT-2-TDS-CODE-REVIEW` (§11.4) on **static P0**; S14 ops gates remain in `TDS_LAUNCH_STATUS.md` / §6.7.
- No new Rn/Dn — no §7 or STATUS defect rows added.
