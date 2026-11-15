# Production reliability launch status

**Branch (PR2):** `bug/post-commit-payment-verify` (from `dev`)  
**Tracker:** [`PRODUCTION_RELIABILITY_DEFECT_REGISTER.md`](./PRODUCTION_RELIABILITY_DEFECT_REGISTER.md) · [`PRODUCTION_RELIABILITY_PR2_CHECKLIST.md`](./PRODUCTION_RELIABILITY_PR2_CHECKLIST.md)

**Last updated:** 2026-11-15  
**Train:** **PR1 merged on `dev`** (PR #14). **PR2 in progress** on branch above.

## PR1 scope (this branch)

| REL | Item | Code |
|-----|------|------|
| REL-016 | `payment.captured` only; ignore `order.paid`; `pay_` keys | `webhooks.py` |
| REL-004 | Check-then-insert; `duplicate_capture` + `duplicate_payment` refund | `webhook_service.py`, migration_037 |
| REL-001 | Dispatch / direct_dispatch `requested` + `paid_at` guard | `dispatch.py` |
| REL-003 | Accept trigger + app pre-check | `triggers.sql`, migration_037, `offer_service.py` |

**Before merge:** preflight `order_%` SQL on staging/prod; `python scripts/apply_migration_037.py`; pytest `tests/test_rel_pr1_dispatch_payment.py`.

**Not in PR1:** REL-002 post-commit (PR2).

## Exit gate (unchanged)

All P0 REL **Verified** on staging before `dev` → `main` — see register + [`MVP_GO_NO_GO_CHECKLIST.md`](./MVP_GO_NO_GO_CHECKLIST.md) §H.