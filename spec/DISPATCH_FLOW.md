# Dispatch flow — booking lifecycle, races, and how each is resolved (v3.2, go-live)

Every guarantee below is enforced by a database mechanism (base schema +
migration 002 in DATABASE.md). App code must handle the resulting errors
gracefully but must NOT reimplement the guarantees. v1 mechanisms were
executed and tested against live PostgreSQL 16 with genuine concurrent
transactions (evidence at bottom); migration-002 objects MUST get the same
concurrent-transaction test treatment before launch.

## Booking state machine (domain='booking' in status_types)

```
payment_pending -> requested          webhook: payment success
payment_pending -> abandoned          sweep: 15-min payment TTL lapsed
payment_pending -> cancelled          customer cancels pre-payment (void, no refund row)
requested       -> confirmed          pujari accepts (trigger 3 writes pujari_id
                                      + status flip + history, atomically)
requested       -> failed_no_pujari   dispatch exhausted (max_rounds, zero accepts);
                                      TERMINAL — sets cancelled_at in the same
                                      transaction + auto full refund
requested       -> cancelled          customer cancels (100% refund)
confirmed       -> requested          pujari cancel (re-dispatch); clears assignment
confirmed       -> cancelled          customer cancels (policy refund)
confirmed       -> in_progress        assigned pujari starts (time-window gated)
in_progress     -> completed          assigned pujari completes
in_progress     -> disputed           support/admin only
```

`abandoned` and `failed_no_pujari` are TERMINAL states in their own right —
they set `cancelled_at` in the same transaction (see below) and never flip to
'cancelled' afterwards; the status preserves WHY the booking died for
support/analytics while `cancelled_at` carries the termination semantics.

Cancellation from `in_progress` or `completed` is IMPOSSIBLE — blocked at the
API (409) and by the `bu_bookings_cancel_guard` trigger. Route to support.
Every transition writes a `booking_status_history` row, no exceptions —
including cancellation, which flips `status_id` to `cancelled` AND sets
`cancelled_at` in the same transaction.

**`cancelled_at` means TERMINATED, not "customer cancelled".** Every terminal
path sets it: customer cancel, the sweep's abandonment flip, and dispatch
exhaustion (`failed_no_pujari`). This is load-bearing: `cancelled_at IS NULL`
is the predicate on both exclusion constraints (frees the pujari window) and
on `ux_bookings_no_duplicate_submit` (lets the customer immediately re-book
the same puja/slot after an abandoned checkout). A terminal status that skips
`cancelled_at` permanently locks that customer out of that slot — this
exact bug is why the rule exists.

## Payment models (`bookings.payment_mode`) — two checkout options

The customer chooses ONE model at checkout; it is snapshotted and immutable.

### Model 1 — `full_online` (marketplace default, Uber/Rapido-style)

```
Customer --[total_amount via Razorpay]--> Platform --[net_pujari_amount payout]--> Pujari bank
```

- `amount_due_online = total_amount`, `amount_due_offline = 0`.
- Dispatch, slot reservation, refunds, GST, and platform fee all work on the
  full captured amount — this is the v2 design unchanged.

### Model 2 — `advance_balance` (configurable advance + rest to pujari directly)

```
Customer --[amount_due_online via Razorpay]--> Platform --[net on advance]--> Pujari bank
Customer --[amount_due_offline cash/UPI]-----> Pujari directly (NOT through platform)
```

- `amount_due_online = LEAST(current_advance, total_amount)` where
  `current_advance` is read live from
  `platform_settings.advance_booking_amount` at checkout time (admin can
  change it any time — see Admin settings below). **Not hardcoded.** Launch
  seed default is ₹250; that is only the initial row in `platform_settings`.
- `amount_due_offline = total_amount - amount_due_online`.
- Razorpay order amount = `amount_due_online` ONLY.
- `paid_at` is set when the **advance** clears — dispatch and slot reservation
  behave identically to full_online (the advance is the commitment signal).
- Platform fee + GST + `payment_splits` are computed on the advance capture
  only — the offline balance is not platform revenue and not in
  `wallet_transactions`.
- **Refunds** (cancel / auto-refund): capped at `amount_due_online`. Policy %
  applies to the advance, never the offline portion. Copy must say so clearly.
- **At service:** pujari app shows "Collect ₹{amount_due_offline} in cash or
  your own UPI/PhonePe." Platform does not process, verify, or escrow the
  offline amount.
- **Acknowledgement:** assigned pujari calls
  `POST /v1/bookings/{id}/confirm-balance-collected` with
  `{method: 'cash'|'upi_direct'}` before `complete` when
  `amount_due_offline > 0`. Sets `balance_collected_*` — audit trail for
  disputes, not a payment gateway event. `complete` returns 409 if balance
  due and not yet acknowledged (pujari cannot mark done without recording
  collection).
- **Disputes** ("customer didn't pay offline"): admin `disputed` flow — no
  Razorpay refund for the offline portion; advance refund only if policy says so.

### Checkout UX (customer app)

Before hold, `GET /v1/checkout/quote` reads the **current** advance from
`platform_settings` and returns both options side by side (example assumes
advance is ₹250 at quote time — values change when admin updates the setting):

```json
{
  "total_amount": 2100.00,
  "advance_amount": 250.00,
  "full_online": {
    "amount_due_online": 2100.00,
    "amount_due_offline": 0,
    "label": "Pay full amount now (UPI / card)"
  },
  "advance_balance": {
    "amount_due_online": 250.00,
    "amount_due_offline": 1850.00,
    "label": "Pay ₹250 now, rest ₹1,850 to pujari at service"
  }
}
```

`advance_amount` in the response is the live setting — client labels MUST use
this field, never a hardcoded ₹250. Changing the admin setting affects **new**
quotes only; amounts on existing bookings are snapshotted at `POST /v1/bookings`.

### Admin advance setting (dynamic, not code)

Stored in `platform_settings` key `advance_booking_amount`:
`{"amount": <decimal>, "currency": "INR"}`. Admin panel:
`GET /v1/admin/settings/advance-booking-amount` and
`PUT /v1/admin/settings/advance-booking-amount` `{amount}`.
Validation: `amount >= 1`, `amount <= 10000` (tune ceiling in app config).
No app redeploy required to change the advance.

Customer picks one → `POST /v1/bookings { ..., payment_mode }`.

## The lifecycle

```
1. SLOT HOLD   customer picks slot (+ optionally a specific pujari)
               -> slot_holds row, expires_at = now() + 5 min
               response carries {hold_id, expires_at, server_time} for the countdown UI
2. BOOKING     POST /v1/bookings {hold_id, ...} — ONE DB transaction:
               a. SELECT hold FOR UPDATE; verify owner + unexpired      -> else 410
               b. Snapshot hold primitives (`slot_date`, `slot_time`,
                  `pujari_id`) as locals before any flush that might abort
               c. INSERT booking: status 'payment_pending',
                  intended_pujari_id = hold.pujari_id (may be NULL),
                  dispatch_mode = 'direct' if pujari chosen else 'broadcast',
                  payment_mode per customer choice ('full_online' |
                  'advance_balance'), snapshotted amount_due_online +
                  amount_due_offline (= total_amount), hold_id persisted.
                  **INSERT … ON CONFLICT DO NOTHING** on
                  `ux_bookings_no_duplicate_submit` (or SAVEPOINT flush in
                  paths that must UPDATE first, e.g. webhooks). Snapshot hold
                  primitives as locals; never read ORM attributes after a failed
                  write. On duplicate: SELECT existing row, return **409** with
                  full checkout payload + `idempotent: true` (never 500).
               d. create Razorpay order for amount_due_online ONLY (external
                  call INSIDE the request, BEFORE commit) — if Razorpay fails,
                  rolls back: a booking without an order can never exist.
                  Persist `bookings.razorpay_order_id` (migration 004) so
                  idempotent retries can resume the same checkout session.
                  (Razorpay-order-without-booking is inert; daily
                  reconciliation voids stale unpaid orders.)
               e. EXTEND the hold: expires_at = now() + 15 min — the hold now
                  covers the realistic Razorpay checkout window. The 5-min TTL
                  only ever kills holds that never reached checkout.
3. PAYMENT     customer completes Razorpay checkout (may take minutes — covered
               by the 15-min hold)
4. WEBHOOK     POST /v1/webhooks/razorpay — verify signature, then ONE transaction:
               a. INSERT payments row (idempotency_key dedupes retries)
               b. SELECT booking FOR UPDATE
               c. if status = 'payment_pending':
                    set paid_at, status -> 'requested', history row,
                    hold: released_at = converted_at = now(),
                    enqueue broadcast_booking(booking_id)
                  if status = 'abandoned' (sweep won the race — payment landed
                  after the 15-min window): DO NOT resurrect. Record payment,
                  INSERT refunds row (reason='late_payment'), notify customer.
                  if ex_bookings_intended_no_overlap raises (another customer
                  paid for this window first): same path — record + auto-refund.
5. BROADCAST   dispatch service creates offers (see "Dispatch" below)
6. ACCEPT      first pujari to accept wins; trigger 3 atomically writes
               bookings.pujari_id AND intended_pujari_id (= committed pujari
               — puts every accepted booking, both dispatch modes, under the
               paid-slot exclusion), flips the booking to 'confirmed', and
               inserts the booking_status_history row (changed_by = the
               accepting pujari's user) — the app layer adds nothing
7. SERVICE     in_progress -> completed; live location + chat active.
               advance_balance: pujari collects offline balance at door,
               confirms via confirm-balance-collected, then completes.
8. SETTLEMENT  payment_splits on amount_due_online; payout to pujari for
               the platform-held portion only. Offline balance appears in
               pujari earnings as informational direct_collection, not a
               wallet credit.
```

## Direct vs broadcast dispatch (`bookings.dispatch_mode`)

The customer either picked a pujari by name/reviews, or asked for anyone.
These are different products — never silently substitute a chosen pujari.

- **direct** (`intended_pujari_id` set): offer goes to that pujari ONLY,
  `expires_at = now() + 10 minutes`. On reject/expiry the customer is asked:
  "Your pujari is unavailable — broadcast to nearby verified pujaris, or
  cancel with full refund?" Their answer flips `dispatch_mode` to 'broadcast'
  (clearing `intended_pujari_id`) or cancels. **Guarded UPDATE** on broadcast
  conversion — 0 rows → 409 if already assigned or no longer direct:
  `WHERE status_id=requested AND dispatch_mode='direct' AND pujari_id IS NULL`.
  Push failure on a direct offer escalates to SMS (MSG91).
- **broadcast** (`intended_pujari_id` NULL, or customer opted in after a
  direct miss): Uber-style rounds, below.

## Dispatch rounds (broadcast mode) — `booking_dispatch_state` row per booking

Radius schedule: **3 km -> 6 km -> 10 km -> 15 km** (rounds 1..max_rounds=4),
values live in `booking_dispatch_state`, tunable per service_area later.

`broadcast_booking(booking_id)` / `rebroadcast_booking(booking_id, fresh=False)`:
0. Ensure dispatch-state row exists: `INSERT INTO booking_dispatch_state (booking_id)
   VALUES (%s) ON CONFLICT (booking_id) DO NOTHING` (worker owns this — callers must not).
1. Redis lock: `SET dispatch_lock:{booking_id} 1 NX EX 60` — not acquired =
   another worker is dispatching this booking; exit.
   **If `fresh=True`** (pujari-cancel / admin return-to-requested): reset
   `round=0, radius_km=3.0, exhausted_at=NULL, last_dispatched=NULL` **here, under the
   lock, before step 2** — never before acquiring the lock (concurrent fresh + sweep
   rebroadcast would double-dispatch round 1).
2. DB compare-and-set: `UPDATE booking_dispatch_state SET round = round + 1,
   radius_km = <schedule[round]>, last_dispatched = now()
   WHERE booking_id = %s AND round = <expected>` — zero rows = this round
   already ran (duplicate task delivery); exit. Even if Redis hiccups, the
   same round can never execute twice.
3. Eligibility query — implementable directly from schema:
   verification_status = 'verified'
   AND EXISTS (SELECT 1 FROM pujari_pricing pp
               WHERE pp.pujari_id = pj.id AND pp.puja_id = b.puja_id)
   AND presence key alive in Redis (`MGET presence:{pujari_id}` over candidates
       — NEVER the pujaris.is_online column)
   AND availability window covers the slot, no unavailability that date
   AND no overlapping active booking (window check vs exclusion semantics)
   AND no overlapping PAID intended window (another booking with
       intended_pujari_id = candidate, paid_at set, uncancelled) — keeps the
       accept-time exclusion_violation rare and the pujari UX clean; the
       constraint itself remains the backstop if this filter is missed
   AND ST_DWithin(pujari_live_location.geom, booking_address.geom, radius_km*1000)
   AND pujari is in an active service_area (pujari_service_areas join)
   AND NOT EXISTS prior booking_assignments row for (booking, pujari) —
       rejectors and expired-ignorers are never re-pinged for the same booking
4. INSERT one booking_assignments row per eligible pujari,
   `expires_at = now() + 2 minutes` (`ux_booking_assignments_one_live` makes
   duplicates impossible even here).
5. FCM push per pujari — best-effort with 2 retries; on UNREGISTERED delete
   the dead devices row. The pujari app's `GET /v1/offers` on foreground is
   the delivery safety net, not the push.
6. Round > max_rounds with zero accepts: booking -> 'failed_no_pujari' AND
   `cancelled_at = now()` (terminal — frees the window and the
   duplicate-submit index), `exhausted_at = now()` on dispatch state,
   INSERT refunds row (reason='no_pujari', 100%), history row, FCM + SMS to
   customer. Loud, honest failure — never a booking stuck in 'requested'
   forever.

## Presence — Redis TTL, not a boolean

- Pujari app on duty: `PUT /v1/me/heartbeat` every 30s (piggybacked on the
  location update — one call writes location + geom + `SET presence:{id} 1 EX 90`).
  **Launch invariant:** heartbeat is the sole writer of `pujari_live_location.geom`
  until partner availability endpoints exist; any future location writer MUST set
  geom (optional defense: `P-PLL-GEOM` trigger in migration 007).
- 3 missed beats (90s) = offline by TTL lapse. App crash/kill needs no
  handling — no stuck-online state is possible.
- Explicit "go offline" deletes the key immediately.
- `pujaris.is_online` is synced lazily by the sweep for admin/analytics only.
  Dispatch NEVER reads it.

## Race matrix — who wins, what the loser sees

| Race | Resolution mechanism | Loser's outcome |
|---|---|---|
| Two customers hold the same slot | `ux_slot_holds_active` partial unique index (`WHERE released_at IS NULL`) | `unique_violation` -> API 409 "slot just taken" |
| Late payment lands after hold expiry, slot re-sold and PAID by someone else | `ex_bookings_intended_no_overlap` (paid, uncancelled bookings only) | `exclusion_violation` in webhook -> record payment + automatic full refund (reason='late_payment'), customer notified |
| Webhook races the abandoned-payment sweep | Both `SELECT booking FOR UPDATE`; first committer decides | Sweep first: webhook sees 'abandoned' -> auto-refund. Webhook first: sweep sees 'requested' -> skips |
| Two pujaris accept the same booking simultaneously | `FOR UPDATE` row lock in `trg_set_booking_pujari_on_accept`; first commit wins | `raise_exception` -> API 409 "booking already taken" |
| Pujari accepts a booking overlapping another of their active bookings | `ex_bookings_pujari_no_overlap` exclusion constraint (btree_gist, duration-aware) | `exclusion_violation` -> API 409 "you have an overlapping booking" |
| Pujari with a PAID direct booking pending elsewhere accepts an overlapping broadcast booking (cross-mode) | trigger 3 writes `intended_pujari_id` on accept -> `ex_bookings_intended_no_overlap` fires | `exclusion_violation` -> API 409 "this overlaps a booking reserved for you" |
| Pujari accepts an offer after it expired | expiry guard in accept trigger (`expires_at <= now()`) | `raise_exception` -> API 410 "offer expired" |
| Pujari accepts after customer cancelled | cancelled guard in accept trigger | `raise_exception` -> API 410 "booking was cancelled" |
| Pujari accepts an offer they already rejected (or one the sweep already expired) | Guard 0 in accept trigger: `OLD.status_id` must be 'offered' | `raise_exception` "already resolved" -> API 410 "offer no longer available" |
| Customer cancels a booking that is in_progress/completed | `bu_bookings_cancel_guard` trigger + API state gate | API 409 "cannot cancel — contact support" |
| Customer double-taps submit | `ux_bookings_no_duplicate_submit` partial unique | `ON CONFLICT DO NOTHING` + existing-row lookup -> API **409** with full checkout payload (`idempotent: true`, includes `razorpay_order_id` when stored). Never 500. |
| Razorpay webhook delivered twice | `payments.idempotency_key UNIQUE` | second insert rejected; handler returns 200 (already processed) |
| Duplicate rebroadcast task delivery (overlapping sweeps, sweep-vs-reject fast path) | Redis dispatch lock + compare-and-set on `booking_dispatch_state.round` + `ux_booking_assignments_one_live` | duplicate no-ops at whichever layer catches it first |
| Refund request retried after gateway timeout | `refunds.id` sent as Razorpay idempotency key + `ux_refunds_one_active_per_payment` | Razorpay dedupes; second live refund row impossible |
| Same user redeems a promo past its per-user limit | `promo_usage_counters` + atomic check-and-increment trigger | `raise_exception` -> API 422 "promo limit reached" |

Key point: the **overlap** constraints are duration-aware. A 10:00 booking for
a 90-minute puja blocks 10:30 for that pujari, not just 10:00 exactly.
`bookings.duration_minutes` is snapshotted from the puja at insert (trigger),
so later catalog changes never reshape existing bookings' windows.

## Cancellation

Gated by current status (API + trigger, see state machine above):

| Status at cancel | Allowed | Refund (platform / Razorpay only) |
|---|---|---|
| payment_pending | yes | nothing captured — void, no refund row |
| requested | yes | 100% of `amount_due_online` |
| confirmed | yes | policy % of `amount_due_online` only (`refund_pct_before_24h` / `after_24h`, Asia/Kolkata). Offline balance (`amount_due_offline`) is never refunded through the platform — if already collected offline, that is between customer and pujari. |
| in_progress / completed / cancelled / abandoned / failed_no_pujari | NO — 409/410 (already terminal or service running) | admin override only (`reason='admin_override'`) |

One transaction: set `cancelled_at`, flip `status_id` to 'cancelled', write
history row, INSERT `refunds` row. Consequences, all automatic:
- The pujari's time window is freed instantly (`cancelled_at IS NULL`
  predicate on both exclusion constraints excludes the row).
- Any still-pending offers on that booking become unacceptable (trigger guard).
- The refund is processed asynchronously — see below. The cancel response
  returns immediately: "refund initiated, 5–7 business days."

Do NOT delete cancelled bookings or their assignments — history stays.

## Guarded transitions (mandatory — `P-TXN-LOCK`)

Every booking write that changes lifecycle state MUST use this pattern in one transaction:

1. `SELECT … FROM bookings WHERE id = :bid FOR UPDATE` (or ORM `with_for_update()`).
2. `UPDATE bookings SET … WHERE id = :bid AND <expected predicates>`.
3. **0 rows updated → 409** (`StaleBookingState` — shared app exception; see API_CONTRACTS.md).

The guard column is not always `status_id`. Examples:

| Transition | Guard predicates |
|---|---|
| Customer cancel | `status_id IN (payment_pending, requested, confirmed)` AND `cancelled_at IS NULL` |
| Pujari start / complete | `status_id = :expected` AND `pujari_id = :assigned` |
| dispatch-choice broadcast | `status_id = requested` AND `dispatch_mode = 'direct'` AND `pujari_id IS NULL` |
| dispatch-choice cancel | same as customer cancel on `requested` — route to `cancellation_service` |
| Pujari cancel | `status_id = confirmed` AND `pujari_id = :self` |

`FOR UPDATE` alone is insufficient if a future handler reads status in Python then
writes without the guard — concurrent committed transitions between read and write
are silently overwritten. Launch-gate tests MUST cover concurrent races (see
`plans/STATUS.md` Sprint 1 concurrency section).

## Pujari cancel (assigned booking dropout) — v3.2

When an assigned pujari cannot perform a `confirmed` booking (schedule conflict,
illness, etc.):

`POST /v1/bookings/{id}/pujari-cancel` — assigned pujari only; NOT allowed from
`in_progress` or later (route to support / admin).

One transaction (app layer; refunds async via worker):
1. Guarded UPDATE per table above (`status_id = confirmed`, `pujari_id = self`).
2. Clear `bookings.pujari_id` and `intended_pujari_id` with history row
   (`changed_by` = pujari user).
3. Flip status per policy — typically back to `requested` for re-dispatch OR
   `cancelled` with customer refund if within customer-cancel policy window.
4. INSERT customer refund row when `amount_due_online` was captured and policy
   applies (same cap as customer cancel on `confirmed`).
5. Enqueue `rebroadcast_booking(booking_id, fresh=True)` if returning to `requested`.
6. Record reliability penalty on pujari (future: dedicated column; launch: log +
   admin queue).

**Launch priority:** Required when bookings can be scheduled &gt;24h ahead.
Same-day-only MVP may defer to admin manual reassign.

## Stuck `confirmed` / no-show (sweep extension) — v3.2 planned

Bookings in `confirmed` where `scheduled_time + grace` (default 90 min,
Asia/Kolkata) has passed without `in_progress`:

- Sweep flags for ops alert (P-MONITOR).
- Product decision at launch: auto customer refund of `amount_due_online` +
  `disputed` status, OR admin-only resolution.

Pujari `start` already requires ±60 min of `scheduled_time`; this handles the
case where pujari never calls `start`.

## Pre-event reconfirmation — v3.2 planned (post-MVP default)

For `scheduled_date - today() > 1 day`: 24h before event, ping assigned pujari
to confirm. No response → admin alert. Optional auto re-dispatch — product
decision. See `spec/plans/SPEC_AMENDMENTS.md` §4.

## Manual reassign (admin) — clear first, then insert

Inserting an accepted assignment for a new pujari while the old one is still
set FAILS on Guard 3 — that is intentional, not a bug. The correct flow, one
transaction:
1. `UPDATE bookings SET pujari_id = NULL, intended_pujari_id = NULL` +
   history row (`changed_by` = the admin) — this frees both exclusion windows.
2. INSERT a booking_assignments row for the new pujari with status
   'accepted' and a short future `expires_at` (e.g. now() + 5 min). The
   INSERT path skips Guard 0 by design; Guards 1–3 and BOTH exclusion
   constraints still validate the new pujari (overlap with their other
   accepted bookings AND with paid direct reservations elsewhere).
3. Trigger 3 re-fires its first-accept block: writes the new pujari onto the
   booking and a fresh 'confirmed' history row (changed_by = the new
   pujari's user — the admin's action is the step-1 row).
Any failure rolls the whole reassign back — the booking is never left
unassigned by a half-completed reassign.

## Refund execution (refund worker) — NEVER inline in a request

Celery `refund_worker` polls `refunds` where status='pending' AND
`next_attempt_at <= now()` (uses `ix_refunds_worker`, `FOR UPDATE SKIP LOCKED`):
- Taking a row: flip to 'processing' AND set `next_attempt_at = now() + 30 min`
  (this doubles as the crash deadline — see requeue below). Commit, THEN call
  Razorpay: the gateway call happens outside any open row lock.
- The idempotency key SENT to Razorpay is `refunds.id` — client-generated and
  stable across retries, so a retry after a timeout can never double-refund.
  The id Razorpay RETURNS (`rfnd_...`) is stored in `gateway_refund_id`.
  (Never the other way round: a value the gateway returns cannot dedupe the
  call that obtains it.)
- Success: status 'succeeded'. Failure: back to 'pending' with exponential
  backoff via `next_attempt_at` (1m, 5m, 30m, 2h, 12h...).
- Requeue rule: a 'processing' row past `next_attempt_at` is a crashed worker
  — flip back to 'pending' (same poll, `ix_refunds_worker` covers both
  statuses). Without this, a crash between 'processing' and completion
  strands the row forever AND blocks any new refund for that payment via
  `ux_refunds_one_active_per_payment`. Razorpay-side idempotency on
  `refunds.id` makes the re-attempt safe even if the crashed attempt
  actually went through.
- After 8 attempts: status 'failed_permanent' + Sentry alert + admin queue
  entry. A refund can stall loudly; it can never vanish silently.
- Daily reconciliation job lists Razorpay-side refunds and cross-checks this
  table — catches "our request timed out but Razorpay actually processed it"
  (fills in `gateway_refund_id`, settles ambiguous requeued rows), and voids
  stale unpaid Razorpay orders from lifecycle step 2c.

## Expiry, abandonment, and re-broadcast (sweep worker)

`workers/sweep_worker.py`, scheduled by Celery Beat every 30 seconds.
Global overlap guard: `SET sweep_lock 1 NX EX 25` — an overlapping beat tick
skips instead of stacking. Row-level safety additionally via
`FOR UPDATE SKIP LOCKED` throughout. Steps:
1. Releases `slot_holds` past `expires_at` (frees abandoned checkouts).
2. Flips `payment_pending` bookings older than 15 min to 'abandoned' AND sets
   `cancelled_at = now()` (+ history row, + release their holds). Setting
   `cancelled_at` is NOT optional — it is what releases
   `ux_bookings_no_duplicate_submit` so the customer can retry the same slot.
   Safe vs the webhook by `FOR UPDATE` on the booking — first committer
   decides. Scan uses `ix_bookings_status_created`.
3. Flips `booking_assignments` still 'offered' past `expires_at` to 'expired'
   AND sets `responded_at = now()` (resolved marker). NOT optional: expired
   rows must leave the `responded_at IS NULL` partial indexes
   (`ix_booking_assignments_sweep`, `ux_booking_assignments_one_live`) or the
   sweep scan grows unboundedly and future re-offers collide.
4. Independently scans for stranded bookings (status='requested', unassigned,
   not cancelled, broadcast before, zero live offers) and fires
   `workers.dispatch.rebroadcast_booking` for each.
5. Lazily syncs `pujaris.is_online` from Redis presence keys (analytics only).

The scan in (4) is deliberately independent of (3)'s output: if a run crashes
midway, the next run recovers the stranded bookings. A booking stays flagged
every cycle until the dispatch service actually creates new offers (the
round compare-and-set makes the repeated firing idempotent) — intended retry
behaviour, not a bug. This same property makes the system self-heal from a
Redis/broker outage: lost tasks are re-detected within 30s of recovery.

**Fast path on last reject:** the reject endpoint, after marking the
assignment rejected, checks "zero live offers remaining?" inline and, if so,
enqueues `rebroadcast_booking` immediately — no 30s wait for a customer
watching the screen. Racing the sweep is safe (dispatch lock + round CAS: one
wins, one no-ops). Offer *expiry* (pujari never responded) intentionally
waits for the sweep — a 0–30s delay there is accepted and by design.

The worker is hygiene + re-dispatch, NOT the safety mechanism: even with the
worker down, the accept trigger independently rejects accepts on expired
offers, and `ex_bookings_intended_no_overlap` independently rejects
double-paid slots.

## Seed-data contract (deployment gate)

`seed.sql` + migration-002 seed rows MUST run before the first booking. The
accept trigger raises a descriptive exception if
`status_types(domain='assignment', code='accepted')` is missing — a deliberate
loud failure. Status ids are always looked up by `(domain, code)`, never
hardcoded, in triggers, worker code, and app code. v2 adds required rows:
`payment_pending`, `abandoned`, `failed_no_pujari`, `disputed`.

## Test evidence

v1 (executed against live PG16):
- Concurrent double-accept: two real psql sessions raced; first committed and
  won, second received the "already accepted" exception and rolled back.
- Overlap: 10:30 booking rejected against a 10:00+90min booking; 11:30
  back-to-back allowed; window freed after cancellation.
- Expired-offer accept and cancelled-booking accept: both rejected.
- Slot re-hold after release: allowed; concurrent active hold: rejected.
- Promo over-limit second redemption: rejected, counter rolled back.
- Sweep worker: 8/8 checks passed including crash-recovery and idempotency.

v2 launch gate — the following MUST be tested the same way before go-live:
- Two concurrent webhook transactions paying for the same pujari window:
  second gets `exclusion_violation` on `ex_bookings_intended_no_overlap`.
- Webhook vs abandoned-sweep race in both orderings.
- Cancel attempt on an `in_progress` booking: rejected by trigger.
- Duplicate `rebroadcast_booking` delivery: round CAS makes second a no-op.
- Refund retry after simulated gateway timeout: no duplicate refund
  (idempotency key + partial unique).
- Accept flips the booking to 'confirmed' and writes EXACTLY ONE history row;
  an idempotent re-accept by the winner writes nothing twice.
- Accept of a previously-rejected assignment: rejected by Guard 0.
- Abandoned booking (sweep sets `cancelled_at`): the same customer can
  immediately re-hold and re-book the identical puja/slot — no
  `ux_bookings_no_duplicate_submit` collision.
- Sweep expiry sets `responded_at`: expired rows leave both
  `responded_at IS NULL` partial indexes; a later round can re-insert an
  offer for a pujari whose earlier offer expired IF dispatch policy ever
  allows it (no unique collision).
- `payment_splits` insert with fee + GST > amount: rejected (trigger raise
  and `ck_payment_splits_net_nonneg`).
- Cross-mode overlap: paid direct booking (intended = P, unaccepted) exists;
  P accepts an overlapping paid broadcast booking -> `exclusion_violation`
  on `ex_bookings_intended_no_overlap` at accept time.
- Idempotent re-accept AFTER `expires_at` has passed: succeeds as a no-op
  (Guard 1 is scoped to fresh accepts) — no spurious "offer expired".
- Stuck 'processing' refund past `next_attempt_at`: requeued to 'pending';
  a previously blocked new refund for that payment becomes insertable once
  the stuck row resolves.
- Manual reassign: clear-then-insert flow succeeds end to end; a direct
  accepted-insert against a still-assigned booking is rejected by Guard 3.
