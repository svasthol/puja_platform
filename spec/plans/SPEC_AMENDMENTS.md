# Spec amendments — v3.2 (approved for development)

This document records additions to the v3 go-live spec from architecture review
(July 2026). Items here are **approved** and have been merged into the normative
spec files where noted. Implementation status is in `plans/STATUS.md`.

---

## 1. Customer booking list

**Added to:** `API_CONTRACTS.md`

- `GET /v1/bookings` — cursor-paginated list of the authenticated customer's
  bookings (newest first). Required for order history in the customer app.

---

## 2. Refund sum cap (money safety)

**Added to:** `DATABASE.md` migration 005; `spec/db/migration_005.sql`

**Problem:** `ux_refunds_one_active_per_payment` prevents two *concurrent* active
refunds but not sequential succeeded refunds summing above `payments.amount`
(e.g. `late_payment` auto-refund succeeded, then `admin_override`).

**Rule:** Before inserting a refund, enforce:

```
SUM(amount) WHERE payment_id = ? AND status = 'succeeded' + new.amount <= payments.amount
```

Implement as DB trigger `trg_refunds_cap_total` or shared service guard.

---

## 3. Pujari cancel + provider dropout

**Added to:** `API_CONTRACTS.md`, `DISPATCH_FLOW.md`

**Problem:** Bookings scheduled days/weeks ahead can sit in `confirmed` if the
assigned pujari becomes unavailable or no-shows. Only customer cancel existed.

**New endpoint:**

- `POST /v1/bookings/{id}/pujari-cancel` — assigned pujari only; booking must be
  `confirmed` (not `in_progress`). One transaction: clear assignment per policy,
  customer notification, optional partial refund per cancellation policy,
  reliability penalty on pujari (future: rating/reliability score).

**Sweep extension (P-SWEEP-CONFIRMED):**

- Bookings `confirmed` past `scheduled_time + grace` (e.g. 90 min) without
  `in_progress` → alert ops + optional auto `disputed` or customer full refund
  of `amount_due_online` per launch policy.

**Launch priority:** Required for far-future bookings; deferrable for same-day-only MVP.

---

## 4. Pre-event reconfirmation (optional launch)

**Added to:** `DISPATCH_FLOW.md` (planned)

For bookings where `scheduled_date - today() > 1 day`:

- 24h before event: FCM/SMS to assigned pujari — confirm or cancel
- No response within 4h: enqueue admin alert; optional auto re-dispatch (product decision)

**Status:** Post-MVP unless launch targets advance scheduling.

---

## 5. Partner onboarding endpoints

**Added to:** `API_CONTRACTS.md`

- `POST /v1/pujari/register` — create pujari profile (`verification_status='pending'`)
- `POST /v1/me/devices` — register FCM `device_token`
- `POST /v1/pujari/documents` — KYC upload (signed S3 URL flow)

---

## 6. Address CRUD + geom invariant

**Added to:** `API_CONTRACTS.md`, `DATABASE.md` migration 005

- `POST/GET/PUT /v1/addresses` — customer addresses
- **Invariant:** every address write MUST set `geom` from lat/lng (app or trigger
  `trg_addresses_geom_sync`). Checkout already rejects `geom IS NULL` (422).

---

## 7. Dispatch eligibility — `pujari_pricing` (correction)

**Corrected in:** `DISPATCH_FLOW.md`

Eligibility step 3 previously said "specialization matches the puja." Schema uses:

- `pujari_pricing (pujari_id, puja_id)` — **primary filter** for "can perform this puja"
- `pujari_specializations` — optional broader skill tags; not sufficient alone

Plans must **not** reference `pujari_pujas` — that table does not exist.

---

## 8. Admin auth — `user_roles` check

**Added to:** `ARCHITECTURE.md`, `API_CONTRACTS.md`

`app_context=admin` on JWT is necessary but not sufficient. Admin dependency
must verify `user_roles` contains `admin` or `support`.

---

## 9. PgBouncer + psycopg3 prepared statements

**Added to:** `ARCHITECTURE.md` connection policy

Behind PgBouncer transaction mode, set `prepare_threshold=None` (disable prepared
statements) on async and sync psycopg3 connections.

---

## 10. Stuck-state monitoring

**Added to:** `ARCHITECTURE.md` monitoring section

Alert in addition to existing (`failed_permanent`, dispatch exhaustion, webhook sig):

| Condition | Alert |
|---|---|
| `payment_pending` past hold TTL + 30 min grace, payment exists | Webhook loss |
| `confirmed` past scheduled_time + 90 min, not `in_progress` | No-show / stuck |
| `refunds` `pending` with `attempt_count >= 6` | Refund stall |

---

## 11. Product policy — `advance_balance`

**Added to:** `ARCHITECTURE.md` (not a code change)

Documented in `plans/MASTER.md`:

- Default UI to `full_online`
- Commission base = `amount_due_online` only (intentional per DATABASE.md)
- Disintermediation risk acknowledged for high-relationship repeat bookings

---

## Migration 005 scope (when implementing §2 and §6)

See `spec/db/migration_005.sql`:

- `trg_refunds_cap_total` trigger
- `trg_addresses_geom_sync` trigger (BEFORE INSERT OR UPDATE on addresses)

Apply via Alembic `op.execute(open("spec/db/migration_005.sql").read())` after 004.

---

## 12. Duration guard (`P-DUR-GUARD`)

**Added to:** `DATABASE.md` migration 006; `spec/db/migration_006.sql`; `spec/db/triggers.sql`

**Problem:** Trigger 5 uses `COALESCE(duration_minutes, 60)`. If `pujas.duration_minutes = 0`,
`COALESCE(0, 60)` stays **0** → empty `tsrange` → both exclusion constraints never fire.

**Fix:**

- Trigger 5: `COALESCE(NULLIF(duration_minutes, 0), 60)` on snapshot from `pujas`.
- `CHECK (duration_minutes > 0)` on `bookings` and `pujas` (migration 006: `NOT VALID` →
  backfill → `VALIDATE CONSTRAINT`).
- Backfill before validate:
  `UPDATE bookings SET duration_minutes = COALESCE(NULLIF((SELECT duration_minutes FROM pujas WHERE id=puja_id),0),60) WHERE duration_minutes IS NULL OR duration_minutes = 0`

---

## 13. dispatch-choice guarded conversion (`P-DIRECT-CLEAR-INTENDED`)

**Added to:** `DISPATCH_FLOW.md`, `API_CONTRACTS.md`

**Problem:** `dispatch-choice` with `action=broadcast` must clear `intended_pujari_id` and
flip `dispatch_mode` to `broadcast`. Without clearing, the declined direct pujari is benched
from re-offer and overlap filters.

**Guarded UPDATE** (0 rows → 409 — not only `status_id`; see §15):

```sql
UPDATE bookings
SET intended_pujari_id = NULL, dispatch_mode = 'broadcast', updated_at = now()
WHERE id = :bid
  AND status_id = :requested_id
  AND dispatch_mode = 'direct'
  AND pujari_id IS NULL;
```

Then enqueue `broadcast_booking(booking_id)` after commit.

---

## 14. Dispatch state reset on fresh re-dispatch (`P-DISPATCH-STATE-RESET`)

**Added to:** `DISPATCH_FLOW.md`

**Problem:** `confirmed → requested` (pujari-cancel) leaves `booking_dispatch_state.round`
at its prior value. Next `rebroadcast_booking` increments from round 3 → 4 → exhaustion.

**Fix:** Reset logic lives in `_dispatch_round` when the task is enqueued with `fresh=True`
(pujari-cancel, admin return-to-requested). Normal reject/sweep rebroadcast uses
`fresh=False` (default) so rounds 1→2→3→4 are unaffected.

**Critical ordering (under the dispatch lock):** acquire `dispatch_lock:{booking_id}` NX
first, then if `fresh=True` reset state, then round CAS, then dispatch. The reset MUST
NOT run before the lock — concurrent `fresh=True` + stale sweep rebroadcast could both
reset and double-dispatch round 1. Sequence: lock → reset (if fresh) → CAS → offers.

```sql
-- inside worker: after dispatch_lock acquired, when fresh=True, before round CAS:
UPDATE booking_dispatch_state
SET round = 0, radius_km = 3.0, exhausted_at = NULL, last_dispatched = NULL
WHERE booking_id = :bid;
```

Pujari-cancel step 4: `rebroadcast_booking.delay(booking_id, fresh=True)`.

---

## 15. Mandatory guarded transitions (`P-TXN-LOCK`)

**Added to:** `DISPATCH_FLOW.md`, `project.mdc`

Every booking state write (status flip **or** mode/assignment predicate change) MUST:

1. `SELECT … FOR UPDATE` the booking row in the same transaction.
2. `UPDATE … WHERE <expected predicates>` — 0 rows → 409 `StaleBookingState`
   ("Booking state changed — refresh and retry."). Application-level, not a DB
   constraint — use one shared exception/helper (see `API_CONTRACTS.md`).

`status_id` alone is not always the guard column (see §13 dispatch-choice). Launch-gate
tests must cover concurrent transitions (customer-cancel vs pujari-start, dispatch-choice
double-tap / late-accept race).

---

## 16. GST / TCS model gate (`P-GST-MODEL`)

**Added to:** `plans/MASTER.md` Phase 3 exit gate; `plans/STATUS.md`

**Problem:** `gst_amount` as a single pct on platform commission assumes GST applies to
commission only. Indian marketplace settlement (GST on puja service vs commission,
unregistered pujaris, e-commerce operator TCS) is unaddressed.

**Rule:** `P-SPLITS` and `P-PAYOUT` are **hard-blocked** until tax advisor sign-off
documents: GST on what, TCS by whom, and how `net_pujari_amount` is computed.
`P-SPLIT-CONFIG` (`commission_pct`, `gst_pct` in `platform_settings`) is necessary but
not sufficient.

---

## Review disposition log (merged reviews — July 2026)

Single audit trail for v3.2 architecture reviews. Implementation status: `plans/STATUS.md`.

### Accepted — fix before or during Phase 0

| ID | Finding | Fix |
|---|---|---|
| P-DUR-GUARD | Zero `duration_minutes` voids exclusion constraints | §12, migration 006 |
| P-DIRECT-CLEAR-INTENDED | dispatch-choice doesn't clear `intended_pujari_id` | §13 |
| P-DISPATCH-STATE-RESET | Dispatch state not reset on `confirmed→requested` | §14, worker `fresh=True` |
| P-TXN-LOCK | Transition handlers need guarded UPDATE pattern | §15 |
| P-SPLIT-CONFIG | No `commission_pct`/`gst_pct` in `platform_settings` | Phase 3 seed + admin API |
| P-GST-MODEL | GST/TCS settlement model undefined | §16, hard block on P-SPLITS |
| — | project.mdc vs pujari-cancel NULL `pujari_id` | carve-out in project.mdc |
| — | Local dev bring-up omits migrations 004–006 | DATABASE.md + conftest |
| P-PLL-GEOM | Optional `pujari_live_location.geom` trigger | P2, migration 007; heartbeat is sole writer today |

### Closed — already implemented or overstated

| Finding | Disposition |
|---|---|
| `booking_dispatch_state` INSERT before CAS | **Closed** — `dispatch.py` L58–63 `ON CONFLICT DO NOTHING` |
| Refund amounts must use `amount_due_online` | **Closed** — dispatch, webhook, cancel paths already correct; migration 005 is backstop |
| `abandoned` without `cancelled_at` | **Rejected** — spec + sweep already set both |
| Silent `failed_no_pujari` from null geom at checkout | **Rejected** — booking returns 422 if `geom IS NULL` |
| Commission on offline portion as undocumented bug | **Rejected** — intentional in DATABASE.md; business policy |
| OTP attempts → CHECK violation | **Mitigated** — app rejects at `attempts >= 5` before increment |
| `pujari_pujas` table | **Rejected** — use `pujari_pricing` |
| Transition locking "all broken" | **Rejected** — cancel/lifecycle use `FOR UPDATE`; guarded UPDATE is mandatory going forward (§15) |
| advance_balance cherry-picking | **Product policy** — documented in MASTER.md, not P0 code |
| No review endpoint | **Post-MVP** — gate on `completed` when added |

### Launch-gate tests (write alongside Phase 0 — not deferred to Phase 6)

- Pujari-cancel at round 3 → next dispatch starts at round 1 / 3 km (`fresh=True`)
- Customer-cancel vs pujari-start concurrent race
- dispatch-choice double-tap / late-accept race (409 on second writer)

---

## Migration 006 scope (when implementing §12)

See `spec/db/migration_006.sql`:

- Trigger 5 `NULLIF` fix
- Backfill `duration_minutes = 0` rows on `pujas` and `bookings`
- `ck_pujas_duration_pos` / `ck_bookings_duration_pos` (`NOT VALID` → `VALIDATE`)

Apply via Alembic `op.execute(open("spec/db/migration_006.sql").read())` after 005.
