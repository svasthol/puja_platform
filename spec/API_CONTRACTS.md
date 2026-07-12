# API contracts — endpoints and the DB-error mapping (v3.2, go-live)

v3.2 adds: customer address CRUD, booking list, partner onboarding, pujari
cancel, device registration. See `spec/plans/SPEC_AMENDMENTS.md`.

FastAPI backend. All authenticated routes take a bearer token; the auth
dependency resolves it via `auth_sessions` and enforces `app_context`
(a customer-app token calling a pujari route -> 403, even for dual-role users).

All list endpoints use cursor pagination: `?cursor=&limit=20` (default 20,
max 50), response carries `next_cursor` (null when exhausted).

## Error mapping — REQUIRED, this is how DB guarantees become good UX

The database raises on every integrity violation (see DISPATCH_FLOW.md).
A shared exception handler must translate `psycopg` errors:

| DB error (constraint / message fragment) | HTTP | Client message |
|---|---|---|
| `unique_violation` on `ux_slot_holds_active` | 409 | "That slot was just taken — pick another time." |
| `raise_exception` "already accepted by a different pujari" | 409 | Pujari app: "This booking was just taken." |
| `exclusion_violation` on `ex_bookings_pujari_no_overlap` | 409 | Pujari app: "This overlaps another booking of yours." |
| `exclusion_violation` on `ex_bookings_intended_no_overlap` (webhook context) | — (webhook-internal) | Not a client error: webhook records the payment, inserts an automatic full refund (reason='late_payment'), notifies the customer. Handler still returns 200 to Razorpay. |
| `exclusion_violation` on `ex_bookings_intended_no_overlap` (accept context — trigger 3 writes `intended_pujari_id`) | 409 | Pujari app: "This overlaps a booking reserved for you." (Should be rare: the dispatch eligibility query filters paid intended windows; the constraint is the backstop.) |
| `raise_exception` "offer expired" | 410 | "This offer has expired." |
| `raise_exception` "already resolved" | 410 | "This offer is no longer available." (pujari tried to accept an offer they rejected, or one the sweep expired) |
| `raise_exception` "was cancelled by the customer" | 410 | "The customer cancelled this booking." |
| `raise_exception` "cannot be cancelled from its current state" | 409 | "This booking can no longer be cancelled — contact support." |
| `unique_violation` on `ux_bookings_no_duplicate_submit` | 409 | Idempotent create — return the **existing** booking checkout payload (same shape as 201, plus `"idempotent": true`). Includes `razorpay_order_id` when stored (migration 004). Client resumes Razorpay checkout on double-tap. |
| `unique_violation` on `payments.idempotency_key` | 200 | Webhook handler: already processed, ack silently. |
| `unique_violation` on `ux_booking_assignments_one_live` | — (dispatch-internal) | Duplicate offer insert from a racing dispatch — skip silently, offer already live. |
| `raise_exception` "usage limit exceeded" | 422 | "This promo code has reached its limit for your account." |
| `raise_exception` "Seed data missing" | 500 + page ops | Deployment gate failed — do not mask this one. |
| `raise_exception` "refunds: total refunded" | 409 | Refund would exceed captured payment amount (migration 005 cap). |
| `StaleBookingState` (guarded UPDATE returned 0 rows — app-level, no DB error) | 409 | "Booking state changed — refresh and retry." Use one shared exception/helper so all transition handlers return the same body. |

Losing a race is a NORMAL flow for the pujari app (Uber drivers see "ride no
longer available" constantly). Design the UI for it; never retry-loop past a 409.

## Endpoint surface (v1 prefix)

### Auth (both apps; `app_context` set from the calling app)
- `POST /v1/auth/otp/request`      {phone} — Redis rate limit: 5/hour per phone
- `POST /v1/auth/otp/verify`       {phone, otp} -> access + refresh tokens.
  Lockout: increment `otp_verifications.attempts` on every failure; at 5,
  reject and require a fresh OTP request. Additionally Redis rate-limit verify
  attempts at 10/hour per phone (stops rotation attacks across OTP rows).
- `POST /v1/auth/refresh`          rotate refresh token (hash stored, UNIQUE)
- `POST /v1/auth/logout`           revoke session (`revoked_at`)

### Customer app
- `GET  /v1/addresses`                         list customer addresses (paginated)
- `POST /v1/addresses`                         {line1, city, latitude, longitude, ...}
  — MUST set `geom` from lat/lng on write (trigger or app; see DATABASE.md
  migration 005). Checkout requires `geom IS NOT NULL` (422 otherwise).
- `PUT  /v1/addresses/{id}`                      update; recompute `geom` when lat/lng change
- `GET  /v1/pujas`                             catalog + categories (paginated)
- `GET  /v1/checkout/quote?puja_id=&addon_ids[]=`  reads the **current**
  `platform_settings.advance_booking_amount` from DB and returns
  `total_amount`, `advance_amount` (live setting), plus both payment options
  (`full_online` and `advance_balance` breakdown per DISPATCH_FLOW.md).
  Client UI labels MUST interpolate `advance_amount` — never hardcode ₹250.
- `GET  /v1/pujaris?puja_id=&date=&time=`      verified pujaris with a
  `pujari_pricing` row for `puja_id`, availability minus unavailability minus
  overlap windows, paginated
- `POST /v1/slot-holds`                        {pujari_id?, date, time} — `pujari_id` omitted = "any pujari" checkout (broadcast mode). 409 if taken. Response:
  `{hold_id, expires_at, pujari_id?, server_time}` — client renders the
  countdown from `expires_at - server_time`, never the local clock. TTL 5 min.
- `POST /v1/bookings`                          {hold_id, puja_id, address_id,
  addon_ids[], promo_code?, payment_mode} —
  `payment_mode`: `'full_online'` | `'advance_balance'` (required). ONE
  transaction: validate hold (`FOR UPDATE`, owner + unexpired, else 410),
  compute and snapshot `total_amount`, `amount_due_online`,
  `amount_due_offline` per DATABASE.md migration 003 rules; insert booking
  status='payment_pending' with `intended_pujari_id`, `dispatch_mode`,
  `hold_id`, `payment_mode` persisted; **INSERT … ON CONFLICT DO NOTHING**
  on `ux_bookings_no_duplicate_submit` (partial unique) so a duplicate never
  aborts the outer transaction — then lookup existing row if no id returned;
  snapshot hold primitives as locals before any write. Snapshot addon prices into
  booking_addons; create
  Razorpay order for `amount_due_online` ONLY BEFORE commit (Razorpay
  failure = full rollback); persist `razorpay_order_id` on the booking row
  (migration 004); extend hold to now()+15 min.
  422 if the address has no `geom` (coordinates not geocoded).
  **201** response: `{booking_id, razorpay_order_id, amount_due_online,
  amount_due_offline, total_amount, payment_mode, hold_expires_at}`.
  **409** idempotent duplicate (double-tap / active booking for same slot):
  same fields plus `"idempotent": true` — client opens Razorpay with the
  returned `razorpay_order_id` or navigates to `GET /v1/bookings/{id}`.
- `POST /v1/bookings/{id}/cancel`              caller must be the booking's customer.
  State-gated (see DISPATCH_FLOW.md cancellation table). Refund amount is
  ALWAYS capped at `amount_due_online` — offline balance is never refunded
  via Razorpay. Atomically: cancelled_at + status flip + history row +
  `refunds` row. Returns refund amount + ETA copy.
- `GET  /v1/bookings`                          customer's bookings, cursor-paginated,
  newest first (`status`, `scheduled_date`, `scheduled_time`, `total_amount`,
  `payment_mode` summary per row)
- `GET  /v1/bookings/{id}`                     status + payment breakdown
  (`payment_mode`, `total_amount`, `amount_due_online`, `amount_due_offline`,
  `balance_collected_at`?) + assigned pujari + history + refund status if any
- `POST /v1/bookings/{id}/dispatch-choice`     {action: 'broadcast'|'cancel'} — on failed
  direct offer. `broadcast`: guarded UPDATE clears `intended_pujari_id`, sets
  `dispatch_mode='broadcast'` WHERE `status=requested AND dispatch_mode=direct AND
  pujari_id IS NULL` (0 rows → 409 `StaleBookingState`); then enqueue `broadcast_booking`.
  `cancel`: route to existing `cancellation_service` (requested → cancelled, 100%
  refund of `amount_due_online`) — same guarded-transition rules; do not implement a
  second cancel path. See DISPATCH_FLOW.md §Direct vs broadcast, §Guarded transitions.
- `WS   /v1/ws/bookings/{id}?ticket=`          live status + pujari location relay + chat (ticket auth below)

### Pujari app
- `POST /v1/pujari/register`                   {bio?, years_experience?} — creates
  `pujaris` row `verification_status='pending'`. KYC required before offers.
- `POST /v1/pujari/documents`                  KYC upload metadata + signed S3 URL
  flow (private bucket). See ARCHITECTURE.md.
- `POST /v1/me/devices`                        {device_token, platform} — FCM target
- `GET  /v1/offers`                            live assignments + payment summary
  per booking (`payment_mode`, `amount_due_offline` when applicable — so the
  pujari sees what to collect before accepting). Polled on foreground.
- `POST /v1/offers/{assignment_id}/accept`     the race endpoint — ONE UPDATE
  setting `status_id` = (assignment, accepted) AND `responded_at = now()`;
  trigger 3 does everything else atomically (assigns the booking, flips it to
  'confirmed', writes history) — the app layer adds NO further writes. Map
  errors per table above. Caller must own the assignment.
- `POST /v1/offers/{assignment_id}/reject`     ONE UPDATE setting `status_id` =
  (assignment, rejected) AND `responded_at = now()`; then fast-path check
  inline: if the booking now has zero live offers, enqueue rebroadcast
  immediately (idempotent — see DISPATCH_FLOW.md)
- `POST /v1/bookings/{id}/start`               assigned pujari only; booking must be 'confirmed' AND now() within ±60 min of scheduled_time (Asia/Kolkata)
- `POST /v1/bookings/{id}/confirm-balance-collected`  assigned pujari only;
  body `{method: 'cash'|'upi_direct'}`. Required before `complete` when
  `payment_mode='advance_balance'` AND `amount_due_offline > 0`. Sets
  `balance_collected_at/by/method` — acknowledgement only, not a gateway
  payment. Idempotent if already collected.
- `POST /v1/bookings/{id}/complete`            assigned pujari only; booking
  must be 'in_progress'. 409 if `advance_balance` with
  `amount_due_offline > 0` and `balance_collected_at` IS NULL.
- `POST /v1/bookings/{id}/pujari-cancel`       assigned pujari only; booking must
  be 'confirmed' (not yet `in_progress`). Clears assignment per DISPATCH_FLOW.md
  §Pujari cancel; customer notified; refund per policy; reliability signal on pujari.
  See `spec/plans/SPEC_AMENDMENTS.md`.
- `PUT  /v1/me/availability` / `/unavailability`
- `PUT  /v1/me/heartbeat`                      body: {lat, lng} — single call writes pujari_live_location (+ geom) AND `SET presence:{pujari_id} 1 EX 90` in Redis. App sends every 30s while on duty. Explicit go-offline: `DELETE /v1/me/heartbeat` (removes the key immediately).
- `GET  /v1/me/earnings`                       per booking: platform_payout
  (from payment_splits/payouts on `amount_due_online`) + direct_collection
  (from `amount_due_offline` where `balance_collected_at` set). Paginated.

### WebSocket auth — single-use ticket (bearer tokens NEVER in URLs)
- `POST /v1/ws-tickets` (normal bearer auth) -> `{ticket, expires_in: 30}`.
  Server stores `ws_ticket:{ticket} = {user_id, app_context}` in Redis, TTL 30s.
- Client connects `wss://.../v1/ws/bookings/{id}?ticket=...`; server `GETDEL`s
  the ticket (single-use — replay from any log is impossible), verifies the
  user is the booking's customer or its assigned pujari, upgrades.
- All WS fan-out is published to Redis channel `booking:{id}` and relayed by
  whichever pod holds the socket (ARCHITECTURE.md rule 6).

### Webhooks
- `POST /v1/webhooks/razorpay`                 verify signature (MUST — reject on mismatch, alert on repeated failures); then the one-transaction flow in DISPATCH_FLOW.md lifecycle step 4: insert payment (idempotency_key dedupe), `FOR UPDATE` booking, flip payment_pending -> requested + convert hold + enqueue broadcast; OR auto-refund path for abandoned/late/double-paid cases. Always 200 to Razorpay once recorded.

### Admin (Next.js panel; role=admin/support only; every action writes history with changed_by)

Admin auth: JWT `app_context=admin` **and** `user_roles` contains `admin` or
`support` (see ARCHITECTURE.md v3.2).
- `GET  /v1/admin/settings/advance-booking-amount`
  -> `{amount, currency, updated_at}` from `platform_settings` key
  `advance_booking_amount`.
- `PUT  /v1/admin/settings/advance-booking-amount`  `{amount}` — updates
  `platform_settings` (validation: `1 <= amount <= 10000`). Takes effect on
  the next `checkout/quote` and new bookings immediately. Does NOT rewrite
  amounts on existing bookings (those were snapshotted at checkout).
- KYC review queue (`pujari_documents` pending), booking search + manual
  reassign — MUST use the clear-then-insert flow in DISPATCH_FLOW.md
  ("Manual reassign"): clear `pujari_id` + `intended_pujari_id` with a
  history row, THEN insert the accepted assignment; inserting while the old
  pujari is still set is rejected by Guard 3 by design —, refund override
  (inserts `refunds` row reason='admin_override'), failed-refund queue
  (`refunds.status='failed_permanent'`), promo CRUD, `service_areas` +
  `pujari_service_areas` CRUD, dispute resolution (in_progress -> disputed;
  offline non-payment disputes).

## Transition authorization matrix (enforce in the auth dependency + handlers)

Guards in the "Required state" column are necessary but not sufficient — handlers must
also use guarded `UPDATE … WHERE <predicates>`; 0 rows → 409 `StaleBookingState`.

| Endpoint | Who may call | Required state |
|---|---|---|
| `/bookings/{id}/cancel` | booking's customer (`app_context=customer`) | payment_pending / requested / confirmed |
| `/bookings/{id}/pujari-cancel` | assigned pujari (`app_context=pujari`) | confirmed only (not in_progress) |
| `/offers/{aid}/accept`, `/reject` | assignment's pujari (`app_context=pujari`) | offer live (unexpired, unresponded) |
| `/bookings/{id}/start` | assigned pujari | confirmed, within ±60 min of scheduled_time |
| `/bookings/{id}/confirm-balance-collected` | assigned pujari | in_progress or confirmed; advance_balance with balance due |
| `/bookings/{id}/complete` | assigned pujari | in_progress; balance acknowledged if due |
| `/bookings/{id}/dispatch-choice` | booking's customer | requested, direct offer failed |
| manual reassign / refund override / dispute | admin role | any (audited) |

## Dispatch service (internal, not an endpoint)

`broadcast_booking(booking_id)` / `rebroadcast_booking(booking_id, fresh=False)`:
full algorithm, eligibility query, round/radius schedule (3/6/10/15 km, max 4),
`fresh=True` dispatch-state reset (pujari-cancel re-dispatch), idempotency (Redis
dispatch lock + `booking_dispatch_state.round` compare-and-set), FCM retry + SMS
fallback, and exhaustion handling (failed_no_pujari + auto-refund) are specified
in DISPATCH_FLOW.md — that document is normative; do not re-derive values here.
