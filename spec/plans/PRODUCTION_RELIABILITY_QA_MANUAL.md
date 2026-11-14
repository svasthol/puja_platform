# Production reliability — QA manual (sign-off)

**Audience:** QA, product, ops  
**Train:** Production hardening plan (`prod_hardening_launch_7e4484af`)  
**Register:** [`PRODUCTION_RELIABILITY_DEFECT_REGISTER.md`](./PRODUCTION_RELIABILITY_DEFECT_REGISTER.md)  
**Status tracker:** [`PRODUCTION_RELIABILITY_LAUNCH_STATUS.md`](./PRODUCTION_RELIABILITY_LAUNCH_STATUS.md)

**Document version:** 2026-11-14  
**Environment:** Staging L2 unless a row says otherwise.

---

## 0. Flutter / mobile build — do you need an app upgrade?

| What you are testing | Customer Flutter upgrade? | Partner Flutter upgrade? |
|----------------------|---------------------------|---------------------------|
| **PR1** (REL-001, 003, 004, 016) — backend only | **No** — use **current store / existing QA build** pointed at **staging API with PR1 + migration 037** | **No** — same |
| **PR2** REL-015 API + MOB-REL-015 (payment-verify) | **Yes** — new build with **MOB-1** after backend PR2 on staging | **No** (P0 money path) |
| **PR4** REL-013 + MOB-REL-013 (503 same hold retry) | **Yes** — **MOB-2** after backend PR4 | **No** |
| Optional MOB-REL-022 (paused bookings copy) | **Yes** — small follow-up if REL-022 shipped | **No** |

**Summary for PR1 QA today:**  
Point the **existing** customer and partner apps at the **staging base URL** where **`bug/dispatch-payment-guards`** (or merged `dev`) is deployed and **`python scripts/apply_migration_037.py`** has been applied. **No new APK/IPA is required** to validate PR1.

If QA uses a **local API** on a laptop, rebuild/restart **API + Celery worker + beat** only — not Flutter.

---

## 1. Preconditions (all PR1 mobile checks)

| # | Gate | Pass? |
|---|------|-------|
| P1 | Staging API is build containing **PR1** (dispatch guards + webhook changes) | ☐ |
| P2 | DB migration **037** applied on staging DB | ☐ |
| P3 | Preflight SQL: no bad `order_%` keys in `payments` (ops — see §10) | ☐ |
| P4 | Customer app **API base URL** = staging (not prod unless signed) | ☐ |
| P5 | Razorpay **test mode**; webhook URL = staging + `payment.captured` enabled | ☐ |
| P6 | Celery **worker + beat** running on staging | ☐ |

---

## 2. Legend

| Column | Meaning |
|--------|---------|
| **Surface** | Customer app · Partner app · Admin · Razorpay/webhook · Script/ops only |
| **PR** | When the fix ships; **N/A** = not in production yet — do not fail QA for missing behaviour |
| **Expected** | Pass criteria |
| **Not expected** | Fail / out of scope / wrong build |

---

## 3. PR1 — test now (REL-001, 003, 004, 016)

### REL-016 — Webhook keying; ignore `order.paid`

| | |
|--|--|
| **Severity** | P0 |
| **Surface** | Razorpay/webhook · Admin (payment rows) |
| **PR** | PR1 (shipped on staging when PR1 deployed) |

**What changed:** Booking payments processed only on **`payment.captured`**. **`order.paid`** must **not** create payment rows. Keys must be **`pay_…`**, not **`order_…`**.

| Steps | Expected | Not expected |
|-------|----------|--------------|
| Ops: preflight SQL (§10) | **Zero** rows with `idempotency_key` or `gateway_txn_id` like `order_%` | Any live `order_` payment keys on paid bookings |
| (Optional) Send test `order.paid` via Razorpay or mock script | HTTP **200**, body like **ignored** / **already_processed**; **no new** `payments` row | New `payments` row with `order_` id |
| Customer pays once (§4 test A) | One `payments` row with **`pay_…`**; booking → **requested** | Payment row keyed by `order_` only; booking stuck unpaid with money taken |

**Mobile alone:** Cannot prove `order.paid` — use webhook logs or ops SQL.

---

### REL-004 — Second capture → refund (not silent `already_processed`)

| | |
|--|--|
| **Severity** | P0 |
| **Surface** | Admin refunds · Razorpay (test double capture) |
| **PR** | PR1 |

**What changed:** Second **different** `pay_…` for an already-paid booking → payment row **`duplicate_capture`** + refund **`duplicate_payment`**.

| Steps | Expected | Not expected |
|-------|----------|--------------|
| Complete one successful customer payment (§4 A) | One `success` payment; booking **requested** | — |
| (Staging test) Trigger second `payment.captured` for same booking with **new** `pay_…` (Razorpay test / script) | Refund row reason **`duplicate_payment`**; second payment status **`duplicate_capture`**; booking stays **requested** (no double-confirm) | Second capture acked with **no** refund row; booking double-confirmed; money stuck with no refund queue |
| Same `pay_…` replay from Razorpay | **already_processed** (idempotent) | New duplicate refund storm |

**Mobile alone:** **Not expected** to test REL-004 — use admin **Failed refunds** / DB or scripted webhook.

---

### REL-001 — Dispatch only when paid `requested`

| | |
|--|--|
| **Severity** | P0 |
| **Surface** | Partner app (indirect) · Celery logs |
| **PR** | PR1 |

**What changed:** Dispatch worker **does not** insert offers if booking is not **`requested`** with **`paid_at`** set.

| Steps | Expected | Not expected |
|-------|----------|--------------|
| Customer completes pay → **requested** (§4 A) | Partner sees **offers** within normal SLA (minutes, not only after unrelated retries) | Offers on booking still **payment_pending** / **abandoned** |
| Partner online, eligible for puja/area | At least one offer or explicit “no pujari” exhaustion per policy | Broadcast offers before customer payment completed |

**Mobile:** Pass **§4 A + §4 B**. Fail only if paid customer never gets offers while pujaris are online and eligible.

---

### REL-003 — Accept only when paid (trigger + API)

| | |
|--|--|
| **Severity** | P0 |
| **Surface** | Partner app · Admin reassign (edge) |
| **PR** | PR1 |

**What changed:** First accept requires **`paid_at`**; admin manual-reassign **INSERT accepted** path preserved.

| Steps | Expected | Not expected |
|-------|----------|--------------|
| Normal: customer paid → partner **Accept** (§4 B) | **Confirmed**; RM assigned per product rules | 409/410 “payment not confirmed” on **normal** just-paid booking |
| (Optional, staging only) Attempt accept on deliberately broken unpaid+offered booking (test data) | Reject / error; booking does not confirm | Confirm without payment |

**Mobile:** Normal accept after §4 A is the main test. Unpaid-accept is **optional** (needs bad test data).

---

## 4. Mobile walkthroughs (customer + partner)

### Test A — Customer checkout (regression + REL-001/016 indirect)

1. Customer app → log in (OTP).  
2. **Catalogue** → select puja → **Book**.  
3. Pick **slot** → continue (hold active).  
4. **Checkout** → select **address** → review **booking fee** / total.  
5. Tap **Pay** → complete Razorpay **test** payment.  
6. **Confirming** screen → wait up to **45 s** (poll).  
7. Open **My bookings** → open this booking.

| Pass (expected) | Fail (not expected) |
|-----------------|---------------------|
| Status **requested** (or flows to dispatch) | Stuck **payment_pending** after Razorpay success |
| Booking detail shows paid / progressing | Endless confirming timeout every time on staging |
| No crash; Telugu/English copy OK | 409 on slot unless idempotent resume handled |

**Note:** App does **not** call payment-verify (REL-015) — **poll-only is still correct** for PR1 QA.

---

### Test B — Partner accept

1. Partner app → log in → **Go online**.  
2. After Test A, open **Offers**.  
3. Open offer → **Accept**.

| Pass (expected) | Fail (not expected) |
|-----------------|---------------------|
| Offer appears after customer Test A | No offers 15+ min with online eligible pujari (investigate) |
| Accept → booking **confirmed** | Accept error on normal paid booking |
| No customer PII beyond spec | — |

---

### Test C — Customer detail / list (smoke)

1. **Bookings list** shows new booking with correct status.  
2. **Booking detail** — schedule, fee breakdown, status timeline sensible.

No new UI for PR1 — **not expected:** new “verify payment” button (comes with MOB-REL-015).

---

## 5. PR2 and later — not expected until shipped (do not fail mobile QA)

Until backend **PR2** is on staging and register row is **On staging**, the following are **N/A** on device:

| ID | Title | Expected when **not** shipped |
|----|--------|------------------------------|
| **REL-002** | Post-commit Celery after webhook | Rare race: paid booking, no offers until sweep — **known until PR2** |
| **REL-005** | Payment reconcile | Lost webhook may need manual ops — **known until PR2** |
| **REL-015** | `POST …/payment-verify` | Route **404/missing** — **expected**; poll-only app **expected** |
| **MOB-REL-015** | Customer payment-verify | **Not in app** — **expected** until MOB-1 build |
| **REL-006** | Post-commit on reject/rebroadcast | Low priority; direct booking off |
| **REL-013** | Two-phase create_order + 503 | Old create flow — **expected** until PR4 |
| **MOB-REL-013** | 503 same `hold_id` retry | **Not in app** — **expected** until MOB-2 build |

When PR2 lands, add a **new QA section** (payment-verify + reconcile scripts).

---

## 6. Full defect register — expected vs not expected (all IDs)

Use **Status** from register: only require **Verified** checks when row is **On staging**.

| ID | P | Shipped in | QA expected (when on staging) | Not expected / N/A |
|----|---|------------|--------------------------------|---------------------|
| REL-001 | P0 | PR1 | §3 REL-001, §4 A–B | Offers before pay |
| REL-002 | P0 | PR2 | Rollback webhook → no dispatch (script) | Proving on mobile only |
| REL-003 | P0 | PR1 | §3 REL-003, §4 B | Confirm without pay |
| REL-004 | P0 | PR1 | §3 REL-004 | Silent second capture |
| REL-005 | P0 | PR2 | Reconcile recovers lost webhook (script) | Mobile-only proof |
| REL-006 | P1 | Deferred | — | N/A at MVP |
| REL-007 | P1 | PR3 | Worker time limits (ops) | Mobile |
| REL-008 | P1 | PR3 | Beat failover (ops) | Mobile |
| REL-009 | P1 | PR3/4 | DB timeout behaviour (ops) | Mobile |
| REL-010 | P1 | PR3 | Alert on reconcile recovery | Alert on every abandon |
| REL-011 | P2 | PR3/4 | — | N/A pre-launch |
| REL-012 | P2 | PR4 | — | TDS off |
| REL-013 | P1 | PR4 | 503 + resume booking (API) | MOB-2 until shipped |
| REL-014 | P2 | PR4 | Accept retry idempotent (API) | — |
| REL-015 | P0 | PR2 | API verify 200/202/403 matrix | In PR1 mobile build |
| REL-016 | P0 | PR1 + PR2 optional | §3 REL-016 | order_ keys in DB |
| REL-017 | P1 | PR3 | Metrics / staging lost-task test | Mobile |
| REL-018 | P1 | PR3 | Worker split (ops) | Mobile |
| REL-019 | P1 | PR4 | Timezone preflight script | Bulk TZ rewrite |
| REL-020 | P1 | PR4 | SQLSTATE mapping (API) | — |
| REL-021 | P1 | PR4 | WS/offers polish | Partner poll rewrite |
| REL-022 | P2 | PR2 | Kill switch 503 holds | MOB-REL-022 optional |
| MOB-REL-015 | P0 | MOB-1 | Verify &lt;10s after pay | In current app for PR1 |
| MOB-REL-013 | P1 | MOB-2 | 503 → same hold retry | In current app for PR1 |
| MOB-REL-022 | P2 | Optional | Maintenance copy on pause | — |
| GATE-REFUND | — | Shipped | Refund idempotency header in prod | — |

---

## 7. Admin console checks (recommended with mobile Test A)

| Area | Path (typical) | Expected after Test A |
|------|----------------|----------------------|
| Booking search | Admin → Bookings → by ID | Status **requested**; `paid_at` set |
| Payments | Booking detail / money | One **success** `pay_…` |
| Refunds | Failed refunds / booking refunds | Empty after happy path |
| After REL-004 test | Refunds | **`duplicate_payment`** row if second capture test run |

---

## 8. Sign-off sheet (PR1 staging)

| Role | PR1 mobile A–B | REL-004/016 ops | Date | Notes |
|------|----------------|-----------------|------|-------|
| QA | ☐ | ☐ | | |
| Eng | ☐ | ☐ | | |
| Product | ☐ | — | | |

**PR1 mobile GO** = P1–P6 + Test A + Test B pass.  
**PR1 full P0 GO** = above + REL-004 webhook test + REL-016 preflight SQL.

---

## 9. Export to PDF

From repo root (`puja_platform`):

```powershell
# If pandoc is installed:
pandoc spec/plans/PRODUCTION_RELIABILITY_QA_MANUAL.md -o spec/plans/PRODUCTION_RELIABILITY_QA_MANUAL.pdf

# Or: open the .md in VS Code / Cursor → Markdown PDF extension, or Print → Save as PDF
```

---

## 10. Ops appendix — preflight SQL (REL-016)

Run on staging (and prod before prod merge):

```sql
SELECT id, booking_id, idempotency_key, gateway_txn_id, status
FROM payments
WHERE idempotency_key LIKE 'order\_%' OR gateway_txn_id LIKE 'order\_%';
```

**Expected:** 0 rows (or documented backfill complete).  
**Not expected:** Rows returned without remediation plan.