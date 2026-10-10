# TDS review run — 2026-09-14

| Field | Value |
|-------|--------|
| Reviewer | Code audit (Cursor agent) — **re-run recommended in fresh chat** with playbook only |
| Scope | Backend accrual worker, statutory load, readiness script |
| Environment | Static analysis (no staging backlog measurement) |

**Note:** Ideal process is a **new session** with only `TDS_CODE_REVIEW.md` + repo. This run documents confirmed static findings; staging falsifiers marked **Not run**.

---

## Verification map results

| ID | Pass/Fail | Notes |
|----|-----------|-------|
| D1 | **Pass** | `service_lifecycle.confirm_balance` calls `enqueue_tds_accrual_intent` only |
| D6 | **Fail (P0)** | Single txn per task; no SAVEPOINT; DB abort poisons batch; `failed`/`attempt_count` may not persist |
| R1 | **Pass** | `test_tds_accrual_decouple` reverses with `TDS_ACCRUAL_ENABLED=false` |
| R4 | **Pass** (correctness) | `FOR UPDATE` without SKIP LOCKED serializes same pujari; ops pool risk remains |
| R15 | **Fail (P1)** | `pricing.load_tds_facilitation_config` — latest row only, not as-of `collected_at` |
| R10 | **Decision** | 027 backfill `operative` for all `pan_hash` — **record for §0.C** (0.1% vs 5%); not auto-pass |
| R8 | **N/A** | `pan_enc` empty by design (P3) |

---

## Findings → register / STATUS

| ID | Action |
|----|--------|
| **R15** | Added §7 2026-09-14; `L-SPRINT-2-TDS-STATUTORY-ASOF` IN_PROGRESS |
| **D6** | Added §7 2026-09-14; `L-SPRINT-2-TDS-WORKER-BATCH-TXN` IN_PROGRESS |

---

## S14 go/no-go (this run)

| Check | Status |
|-------|--------|
| No open P0 Fail | **No** — D6 open |
| Poison-pill quarantine proven | **Not run** — falsifier documented in playbook §6.2 |
| Backlog batch duration measured | **Not run** — needs staging |
| Reconcile green | **Not run** |

**Verdict:** **Do not flip** `TDS_ACCRUAL_ENABLED` until D6 fixed + re-review.

---

## §0.C inputs

- **Readiness script:** exposure uses `float` (`nopan_gross * 0.05`) — treat as indicative until Decimal or doc label.
- **R10 backfill:** Owner should confirm whether backfilled `operative` is acceptable; if not, exposure model changes.

---

## Recommended next steps

1. Fix D6 (SAVEPOINT + bounded intents per task).  
2. Fix R15 (statutory as-of `collected_at`).  
3. Add pytest that fails on reverted D6/R15 fixes.  
4. **Fresh-session** re-run → new `TDS_REVIEW_*.md` with staging measurements.  
5. Then S14 staging flip per updated gate row.
