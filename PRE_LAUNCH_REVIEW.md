# Pre-launch review — issues, blindspots, and fix plan

**Review date:** 2026-09-12  
**Scope:** Refunds (A), dispatch exhaustion (B), RM assignment (D), admin monitoring, ops/data hygiene. SMS (C) skipped per review scope.  
**Evidence:** Live PostgreSQL (`Mana_Guruji`), Celery/API logs, micro-test of real `accept_offer` path, admin SQL screenshots.

This document separates **false alarms** (logs that look scary but are spec-correct) from **real pre-launch work** (ops, code, admin, supply). Use it as a launch checklist.

---

## Executive summary

| Category | Verdict | Action before launch |
|----------|---------|----------------------|
| Refund worker core logic | ✅ Spec-correct | Improve error classification; ops queue for stuck rows |
| Dispatch exhaustion (`failed_no_pujari`) | ✅ Spec-correct | Fix **supply** (online pujaris); monitor rate |
| `rm_assigned_on_confirm` log line | ✅ Success event, not error | Backfill 10 historical rows; harden edge cases |
| Stuck refunds (404/400 on Razorpay) | ⚠️ Real ops issue | Manual cleanup + fail-fast on permanent gateway errors |
| Admin end-to-end monitoring | ⚠️ Gap | Pending-refund queue + console widgets (partial exists today) |
| Test/seed data pollution | ⚠️ Noise | Don't use polluted DB metrics for go/no-go |

**Bottom line:** Core booking/dispatch/refund **engines are not broken**. Launch risk is **money stuck in retry**, **high no-pujari rate**, **ops blind spots**, and **historical data gaps** — not the alarm log lines themselves.

---

## 1. False alarms — NOT bugs (do not “fix” the worker)

These log patterns are **designed behaviour** per `spec/DISPATCH_FLOW.md`. Fixing them would mean changing the spec.

### 1.1 `refund_retry` → `refund_failed_permanent` → `alert_refund_failed`

- **What it means:** Refund worker tried Razorpay up to 8 times, then marked the row `failed_permanent` and alerted ops.
- **Why it exists:** Gateway timeouts can be transient; idempotent retries prevent double-refund.
- **Live DB (2026-09-12):** 4 `failed_permanent` (2 real Razorpay 400 `no_pujari`, 2 seed `admin_override` with generic `"gateway error"`).

### 1.2 `dispatch_exhausted` → `failed_no_pujari`

- **What it means:** No pujari accepted within the dispatch deadline; booking terminated; auto-refund row inserted when payment succeeded.
- **Live DB:** 159 `failed_no_pujari`; invariants hold (`cancelled_at` set, 0 with `pujari_id`, 0 paid-without-refund).

### 1.3 `rm_assigned_on_confirm`

- **What it means:** INFO log — RM was successfully written after pujari accept.
- **Micro-test proof:** Real `accept_offer` assigns default RM (`rowcount: 1`) for both `advance` and `instant`.

---

## 2. Real issues — fix before launch

Prioritized: **P0** = money or customer trust at risk; **P1** = launch quality; **P2** = improve ops efficiency.

---

### P0-1 — Stuck refunds retrying on permanent Razorpay errors

**Symptom (your SQL):**

```
status=pending, attempt_count=5 → 46 rows
status=failed_permanent, attempt_count=8, reason=no_pujari → 2 rows (400 Bad Request)
status=failed_permanent, attempt_count=5, reason=admin_override → 2 rows ("gateway error" — seed)
```

**Plain language:** App tells customer “refund initiated,” but Razorpay says “I don’t know this payment” (404) or “can’t refund this” (400). Worker keeps retrying until attempt 8.

**Why it happens:**

| Error | Meaning | Typical cause |
|-------|---------|---------------|
| 404 Not Found | Payment ID unknown to Razorpay | Wrong account (test vs live), deleted payment, invalid/seed `gateway_txn_id` |
| 400 Bad Request | Refund rejected | Already refunded, not captured, wrong amount, test payment not refundable |

**How it hurts the app:** Customer waits days; support tickets; trust loss even when booking correctly failed.

**High-level fix:**

1. **Ops (immediate):** Daily query on `pending` refunds with `attempt_count >= 3`; resolve in Razorpay dashboard or manual UPI; update `refunds.status`.
2. **Code:** Classify Razorpay 4xx as **non-retriable** → `failed_permanent` on first permanent error (or after 1 attempt), not after 8. Keep retries for 5xx/timeouts only.
3. **Data:** Ensure `payments.gateway_txn_id` always matches Razorpay **capture** id from webhook (not order id).
4. **Admin:** Add **Pending refunds** page (today only `failed_permanent` queue exists at `/console/refunds`).

**Verification SQL:**

```sql
SELECT id, booking_id, amount, attempt_count, reason, left(last_error, 80)
FROM refunds
WHERE status = 'pending'
ORDER BY attempt_count DESC, next_attempt_at;
```

**Acceptance:** No `pending` refund older than 48h with `attempt_count >= 3` without ops ticket; 4xx → `failed_permanent` within 1 attempt.

---

### P0-2 — High dispatch failure rate (`failed_no_pujari`)

**Symptom:** 159 `failed_no_pujari` vs 122 `confirmed` in live DB.

**Plain language:** Customer paid, app could not find an available pujari in time.

**Why it happens (supply, not refund bug):**

- Pujaris offline (no Redis `presence:{id}` heartbeat).
- Missing `pujari_pricing` or `pujari_service_areas`.
- Advance inbox cap (15 live offers per pujari).
- Dev/test bookings without real partners.

**How it hurts the app:** “App never finds a pujari” — worst launch perception.

**High-level fix:**

1. **Supply:** Ensure verified pujaris in launch city are online during peak hours; A-KYC promotion runs `ensure_partner_dispatch_readiness()`.
2. **Monitor:** Daily count of new `failed_no_pujari`; alert if rate &gt; X% of paid bookings.
3. **RM escalation:** Already fires (`rm_dispatch_escalation_sent`) — ensure RM team process exists.
4. **Staging:** Use realistic partner count before judging 159 as prod risk (may be test noise).

**Verification SQL:**

```sql
SELECT date_trunc('day', b.updated_at) AS day, count(*)
FROM bookings b
JOIN status_types st ON st.id = b.status_id AND st.domain = 'booking' AND st.code = 'failed_no_pujari'
GROUP BY 1 ORDER BY 1 DESC LIMIT 14;
```

**Acceptance:** &lt; 20% of **paid** bookings end `failed_no_pujari` in staging soak with real online pujaris.

---

### P1-1 — Confirmed bookings missing Relationship Manager (10 rows)

**Symptom:**

```sql
-- Real pujari accepts (history changed_by set) but relationship_manager_id IS NULL
→ 10 rows (all booking_class = advance, address city = Hyd)
```

**Plain language:** Booking confirmed but customer/pujari may not see RM contact in app.

**Why it happens:**

- Historical: accepts before `P-LAUNCH-RM` or before `default_relationship_manager_id` was set.
- **Not** a current `accept_offer` bug (proven 2026-09-12).
- **Blindspot:** `assign_rm_on_confirm` is **soft-fail** — accept succeeds even if no RM resolves (`no_rm_available_for_booking` warning only).
- **Blindspot:** `admin_reassign` does **not** call `assign_rm_on_confirm`.

**High-level fix:**

1. **One-time backfill** (see §5).
2. **Code:** Optionally fail accept if no RM when launch policy requires it, OR enqueue ops alert on `no_rm_available_for_booking`.
3. **Code:** Call `assign_rm_on_confirm` from `manual_reassign` when `relationship_manager_id IS NULL`.

**Verification SQL:**

```sql
SELECT b.id, b.booking_class, b.relationship_manager_id
FROM bookings b
JOIN status_types st ON st.id = b.status_id AND st.domain = 'booking' AND st.code = 'confirmed'
WHERE b.relationship_manager_id IS NULL
  AND EXISTS (
    SELECT 1 FROM booking_status_history h
    JOIN status_types s3 ON s3.id = h.status_id AND s3.domain = 'booking' AND s3.code = 'confirmed'
    WHERE h.booking_id = b.id AND h.changed_by IS NOT NULL
  );
```

**Acceptance:** 0 confirmed bookings without RM after backfill; new accepts always have RM when default RM is active.

---

### P1-2 — Refund worker does not distinguish retriable vs permanent errors

**Location:** `app/workers/refund.py` — all exceptions share same retry path.

**High-level fix:**

- Parse Razorpay HTTP status / error body.
- **Retriable:** 5xx, timeouts, network → existing backoff.
- **Permanent:** 400, 404, “already refunded” → `failed_permanent` + alert immediately.

**Acceptance:** Unit test with mocked 404 → single attempt, `failed_permanent`.

---

### P1-3 — Admin cannot monitor “every transaction start to end” in one place

**What exists today:**

| Admin page | Coverage |
|------------|----------|
| `/console/bookings` | List |
| `/console/bookings/{id}` | 360° — history, assignments, payments, refunds, dispatch, address |
| `/console/refunds` | **`failed_permanent` only** |

**Gaps:**

- No **pending/processing refunds** queue.
- No console home widget for dispatch failures or stuck refunds.
- No unified lifecycle timeline (quote → hold → pay → dispatch → accept → complete).
- Documented in `spec/plans/OBSERVABILITY_GAPS.md` (Phase 7).

**High-level fix (minimum for launch):**

1. Admin page: **Pending refunds** (`status IN ('pending','processing')`, sort by `attempt_count`).
2. Console home: counts — `failed_permanent` refunds, `failed_no_pujari` (24h), `payment_pending` &gt; 15m.
3. Daily ops runbook (§4).

**Acceptance:** Ops can find any stuck money without writing SQL.

---

### P2-1 — Seed / test data pollutes metrics

**Symptom:**

- `booking_dispatch_state.round` = 37, 52 with `max_rounds = 4` (impossible via code).
- `failed_permanent` at `attempt_count = 5` with `"gateway error"` (not worker httpx format).

**High-level fix:** Separate staging DB from dev seed scripts; or tag test bookings and exclude from ops dashboards.

---

### P2-2 — SMS delivery failures (skipped in review, still launch-relevant)

- `fast2sms` 400, `msg91` disabled → `sms_txn_all_providers_failed`.
- TRAI DLT required for India (`project.mdc`).
- RM escalations may not reach pujaris by SMS if DLT not approved.

**High-level fix:** Complete DLT registration; use `DEBUG=true` + `otp_dev_only` in dev only; monitor `sms_txn_all_providers_failed` in prod.

---

### P2-3 — FCM invalid tokens

- `fcm_push_exhausted` — self-heals via `fcm_device_removed`.
- Not a launch blocker; poll + `GET /v1/offers` are safety nets.

---

## 3. Code blindspots (design gaps, not crashes)

| ID | Gap | File(s) | Risk |
|----|-----|---------|------|
| BL-1 | Refund 4xx retried 8× | `app/workers/refund.py` | Delayed ops visibility, customer wait |
| BL-2 | RM assign soft-fail on accept | `app/services/relationship_manager.py`, `offer_service.py` | Confirmed booking without RM |
| BL-3 | Reassign skips RM assign | `app/services/admin_reassign.py` | Reassigned booking may lack RM |
| BL-4 | No Razorpay reconciliation job wired in admin UI | spec mentions daily reconciliation | Ambiguous “processing” refunds after worker crash |
| BL-5 | Observability happy-path gaps | `spec/plans/OBSERVABILITY_GAPS.md` | Hard to debug customer journeys |

---

## 4. Daily ops runbook (until admin queues ship)

Run once per day (or on-call):

1. **Failed refunds** — Admin → `/console/refunds`.
2. **Stuck refunds:**
   ```sql
   SELECT id, booking_id, amount, attempt_count, left(last_error, 60)
   FROM refunds WHERE status = 'pending' AND attempt_count >= 3;
   ```
3. **Dispatch failures (24h):**
   ```sql
   SELECT count(*) FROM bookings b
   JOIN status_types st ON st.id = b.status_id
   WHERE st.code = 'failed_no_pujari' AND b.updated_at > now() - interval '24 hours';
   ```
4. **Confirmed without RM:**
   ```sql
   SELECT count(*) FROM bookings b
   JOIN status_types st ON st.id = b.status_id
   WHERE st.code = 'confirmed' AND b.relationship_manager_id IS NULL;
   ```
5. **Any customer complaint** → Admin booking detail → check **Payments** then **Refunds** then **Dispatch state**.

---

## 5. One-time data fixes (run in staging first)

### 5.1 Backfill RM on confirmed bookings

Only when `default_relationship_manager_id` is set and RM is active:

```sql
-- PREVIEW
SELECT b.id FROM bookings b
JOIN status_types st ON st.id = b.status_id AND st.code = 'confirmed'
WHERE b.relationship_manager_id IS NULL;

-- APPLY (after preview)
UPDATE bookings b
SET relationship_manager_id = (
  SELECT (value_json->>'relationship_manager_id')::uuid
  FROM platform_settings WHERE key = 'default_relationship_manager_id'
),
updated_at = now()
FROM status_types st
WHERE st.id = b.status_id AND st.code = 'confirmed'
  AND b.relationship_manager_id IS NULL
  AND EXISTS (
    SELECT 1 FROM relationship_managers rm
    WHERE rm.id = (SELECT (value_json->>'relationship_manager_id')::uuid
                   FROM platform_settings WHERE key = 'default_relationship_manager_id')
      AND rm.is_active
  );
```

### 5.2 Mark hopeless refunds for manual ops

For rows with Razorpay 404/400 in `last_error` after ops verifies payment state in Razorpay dashboard — update status or create `admin_override` refund with correct payment id. **Do not bulk-update without checking each payment in Razorpay.**

---

## 6. Suggested implementation order

| Order | Task | Owner | Effort |
|-------|------|-------|--------|
| 1 | Ops: clear / triage 46 pending refunds at attempt 5 | Ops | 1–2 days |
| 2 | Code: Razorpay error classification in refund worker | Backend | Small |
| 3 | Admin: Pending refunds page | Backend + admin_ui | Medium |
| 4 | Data: RM backfill + verify default RM setting | Ops/DB | Small |
| 5 | Supply: pujari online / pricing / areas audit | Ops + product | Ongoing |
| 6 | Code: `assign_rm_on_confirm` on manual reassign | Backend | Small |
| 7 | Admin: console home metrics widgets | Backend + admin_ui | Medium |
| 8 | DLT / SMS prod readiness | Ops | External |

---

## 7. Launch checklist

- [ ] `default_relationship_manager_id` set; default RM `is_active = true`
- [ ] Razorpay **live** keys in prod; webhook secret matches dashboard
- [ ] Stuck refunds triaged; no `pending` with `attempt_count >= 3` without owner
- [ ] `failed_permanent` queue empty or each row has ops ticket
- [ ] Staging soak: paid booking → accept → RM visible on customer + pujari detail
- [ ] Staging soak: paid booking → no pujari → refund succeeds or `failed_permanent` within SLA
- [ ] At least N verified pujaris online in launch city during test window
- [ ] SMS DLT status documented (or RM phone process if SMS fails)
- [ ] Celery beat + worker running (`sweep`, `process_refunds`, dispatch beat tasks)
- [ ] `/health` shows `sweep_stale = false` (`spec/SWEEP_RELIABILITY.md`)

---

## 8. Reference — live DB snapshot (2026-09-12)

| Metric | Value |
|--------|-------|
| Bookings total | 520 |
| `failed_no_pujari` | 159 |
| `confirmed` | 122 |
| Refunds `pending` | 47 (46 at attempt 5) |
| Refunds `failed_permanent` | 4 |
| Refunds `succeeded` | 9 |
| Confirmed, real accept, no RM | 10 |
| Active RMs | 106 |

---

## 9. Related spec / code

- `spec/DISPATCH_FLOW.md` — refund worker, dispatch exhaustion, RM after confirm
- `spec/plans/LAUNCH_POLICY.md` — RM, broadcast-only, booking_fee
- `spec/plans/OBSERVABILITY_GAPS.md` — monitoring gaps
- `app/workers/refund.py` — refund execution
- `app/workers/dispatch.py` — `exhaust_booking_no_pujari`
- `app/services/relationship_manager.py` — `assign_rm_on_confirm`
- `admin_ui/src/app/console/refunds/page.tsx` — failed_permanent queue only

---

*Update this file when items are fixed; link PRs/commits next to each P0/P1 row.*
