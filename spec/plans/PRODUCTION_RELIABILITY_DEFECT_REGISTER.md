# Production reliability defect register (REL)

**Status workflow:** `Open` → `In PR` → `On staging` → `Verified` → `Closed`  
**Launch:** [`PRODUCTION_RELIABILITY_LAUNCH_STATUS.md`](./PRODUCTION_RELIABILITY_LAUNCH_STATUS.md)

## PR1 (`bug/dispatch-payment-guards`) — In PR

| ID | Status | Tests |
|----|--------|-------|
| REL-001 | In PR | `tests/test_rel_pr1_dispatch_payment.py` |
| REL-003 | In PR | trigger + `offer_service` |
| REL-016 | In PR | `webhooks.py` |
| REL-004 | In PR | duplicate capture + refund |

Full backlog: see plan `prod_hardening_launch_7e4484af` (remaining rows **Open** until their PR).

---

## Manual QA findings (2026-11-14) — **not PR1**

Pre-staging smoke reported while reviewing `bug/dispatch-payment-guards`. None of these are caused by REL-001/003/004/016; track on separate `bug/*` or `feature/*` branches after PR1 merges.

| ID | Severity | Symptom | Likely area | Plan / REL linkage |
|----|----------|---------|-------------|-------------------|
| QA-DISP-001 | P1 | Newly onboarded partner does not see existing advanced/instant offers | Dispatch only creates offers per **reconcile round** for eligible online pujaris; no backfill of live `booking_assignments` to newcomers | Product/ops gap — not in prod hardening plan; may need `reconcile` sweep or explicit “catch-up” when partner goes `verified` + online |
| QA-DISP-002 | P2 | Slot year **2038** still shown as **instant** offer (expected advance) | Test/far-future slots + `booking_class` at book time vs `urgency` at `GET /v1/offers` (live `lead_hours`) | Related to flaky integration tests (`skipped: deferred` on 2038); fix validation on slot hold/create — **not PR1** |
| QA-DISP-003 | P1 | Two partners accept same offer; loser does not see “already taken by another guruji” | Backend: `409` + `BookingAlreadyTakenError` (REL-003). Partner app: `offers_controller.dart` maps `409` → `bookingTaken` — if no toast, UI may not surface `OfferAcceptOutcome.error` | **REL-014** (PR4 partner UX / accept feedback); verify API returns **409** not generic error |
| QA-DISP-004 | — (question) | After puja complete + partner ends booking, when do instant/advanced offers resume? | **Policy:** overlap exclusion until slot end + travel buffer (`dispatch_buffer_minutes` / P-LAUNCH-BUFFER ~60m soft at accept); `reoffer_cooldown_minutes` (default **45**) for expired ignorers; partner must be **online** + Redis presence for instant rounds | Document in QA manual §dispatch; not a defect unless observed cooldown exceeds spec |
| QA-BOOK-005 | P2 | Enforce **90-day** max booking horizon (no puja after 3 months) | Customer slot picker + `POST` book validation | New product rule — **not in plan**; add `max_booking_horizon_days` gate (API + Flutter) |
| QA-KYC-006 | **P0** | Profile photo change → `GET /v1/pujari/kyc/status` **500**; partner app broken | `partner_kyc_service._photo_change_under_review` (~L1000): `.scalar_one_or_none()` on multiple `pujari_documents` (`is_current=false`, `status=verified`) → `MultipleResultsFound` | **Urgent hotfix** `bug/kyc-photo-status-500` — use `ORDER BY uploaded_at DESC LIMIT 1` or `.scalars().first()`; optional DB dedupe constraint |

### QA-KYC-006 (log anchor)

```
partner_kyc_service.py:1000 _photo_change_under_review → MultipleResultsFound
GET /v1/pujari/kyc/status → 500
```

**Recommended order:** merge PR1 → hotfix **QA-KYC-006** → PR2 (REL-002 post-commit, payment reconcile) → address QA-DISP-001/003/005 in planned or ad-hoc PRs.