# API contracts — endpoints and the DB-error mapping (v3.4, go-live)

v3.2 adds: customer address CRUD, booking list, partner onboarding, pujari
cancel, device registration.

**v3.3 adds (Flutter backend contract — SPEC_AMENDMENTS §23):** `GET /v1/app-config`
(public), server-cached `GET /v1/panchangam`, `booking_class` on customer booking
reads + create response, `is_muhurat_bound` on customer catalog, `advisory_booking_class`
+ `gate_warnings` on slot-holds, `POST /v1/pujari/bookings/{id}/reconfirm`.
OpenAPI artifact for mobile codegen (see §OpenAPI).

**v3.4 adds (panchangam home-ribbon — SPEC_AMENDMENTS §23.6, migration 018):**
`vaaram`, `yama_gandam`, `sunrise`, `sunset` on `GET /v1/panchangam`; vendor mapping
from `@ishubhamx/panchangam-js` / self-hosted telugu-panchangam-app adapter.

**Puja MVP launch policy:** §21. See `spec/plans/LAUNCH_POLICY.md`.

FastAPI backend. All authenticated routes take a bearer token; the auth
dependency resolves it via `auth_sessions` and enforces `app_context`
(a customer-app token calling a pujari route -> 403, even for dual-role users).

All list endpoints use cursor pagination: `?cursor=&limit=20` (default 20,
max 50), response carries `next_cursor` (null when exhausted).

## Launch policy (SPEC_AMENDMENTS §21) — API summary

**Broadcast-only checkout.** Direct booking and `dispatch-choice` are **not exposed**
at launch. `dispatch_mode` is always `'broadcast'`; `intended_pujari_id` is NULL at
checkout (trigger 3 still sets it on accept — do not remove).

| Topic | Launch behaviour |
|-------|------------------|
| Area | `service_area_id` required on address; `GET /v1/service-areas` for dropdown |
| Offers | Area label only — no customer address/phone; `urgency` + `urgency_escalated` for modal/inbox (§21.6.E) |
| After confirm | Customer: pujari + RM. Pujari: address + map link + RM |
| Heartbeat | `{lat,lng}` optional; presence required |
| WS | Status events only — **no** pujari location relay at launch |
| Booking gate | `POST /v1/bookings` freezes `booking_class` + applies night gate before Razorpay (§21.6.A) |
| Client config | `GET /v1/app-config` — public read of `night_bookings_enabled`, `instant_lead_hours` (no hardcoded night filter in apps) |
| Panchangam | **Server-cached** `GET /v1/panchangam` — mobile apps do not call vendor APIs directly (§23) |
| Dispatch | **Immediate on payment** for all classes (§21.6.C); webhook only enqueues |

Full rules: `spec/plans/LAUNCH_POLICY.md`, `DISPATCH_FLOW.md` §Puja MVP launch dispatch + §Dispatch windows.

**Dispatch v2 booking-gate 422s (§21.6.A):**
- `INSTANT_NIGHT_BLOCKED` — instant-class booking for a 00:00–05:59 IST slot (permanent).
- `NIGHT_BOOKINGS_DISABLED` — any night slot while `night_bookings_enabled=false` (launch 2a).

Both are returned by `POST /v1/bookings` **before** the Razorpay order is created (no payment taken).

## Error mapping — REQUIRED, this is how DB guarantees become good UX

The database raises on every integrity violation (see DISPATCH_FLOW.md).
A shared exception handler must translate `psycopg` errors:

| DB error (constraint / message fragment) | HTTP | Client message |
|---|---|---|
| `unique_violation` on `ux_slot_holds_active` | 409 | "That slot was just taken — pick another time." |
| `raise_exception` "already accepted by a different pujari" | 409 | Pujari app: "This booking was just taken." |
| `exclusion_violation` on `ex_bookings_pujari_no_overlap` | 409 | Pujari app: "This overlaps another booking of yours." **Launch:** also use for soft travel-buffer reject at accept (§21.5) with distinct copy: "Too close to your previous booking — travel time needed." Admin reassign (`A-REASSIGN`): "Target pujari has an overlapping booking in that window." |
| `exclusion_violation` on `ex_bookings_intended_no_overlap` (webhook context) | — (webhook-internal) | Not a client error: webhook records the payment, inserts an automatic full refund (reason='late_payment'), notifies the customer. Handler still returns 200 to Razorpay. |
| `exclusion_violation` on `ex_bookings_intended_no_overlap` (accept context — trigger 3 writes `intended_pujari_id`) | 409 | Pujari app: "This overlaps a booking reserved for you." (Should be rare: the dispatch eligibility query filters paid intended windows; the constraint is the backstop.) |
| `raise_exception` "offer expired" | 410 | "This offer has expired." |
| `raise_exception` "already resolved" | 410 | "This offer is no longer available." (pujari tried to accept an offer they rejected, or one the sweep expired) |
| `raise_exception` "was cancelled by the customer" | 410 | "The customer cancelled this booking." |
| `raise_exception` "cannot be cancelled from its current state" | 409 | "This booking can no longer be cancelled — contact support." |
| `unique_violation` on `ux_bookings_no_duplicate_submit` | 409 | Idempotent create — return the **existing** booking checkout payload (same shape as 201, plus `"idempotent": true`). Includes `razorpay_order_id` when stored (migration 004). Client resumes Razorpay checkout on double-tap. |
| `unique_violation` on `payments.idempotency_key` | 200 | Webhook handler: already processed, ack silently. |
| `unique_violation` on `ux_booking_assignments_one_live` | — (dispatch-internal) | Duplicate offer insert from a racing dispatch — skip silently, offer already live. |
| `unique_violation` on `ux_refunds_one_active_per_payment` | 409 | Admin (`A-REFUND`): "A refund is already in progress for this payment." Webhook/internal idempotent path may ack 200 `refund_already_active`. |
| `raise_exception` "usage limit exceeded" | 422 | "This promo code has reached its limit for your account." |
| `raise_exception` "Seed data missing" | 500 + page ops | Deployment gate failed — do not mask this one. |
| `raise_exception` "refunds: total refunded" | 409 | Refund would exceed captured payment amount (migration 005 cap). |
| `StaleBookingState` (guarded UPDATE returned 0 rows — app-level, no DB error) | 409 | "Booking state changed — refresh and retry." Use one shared exception/helper so all transition handlers return the same body. |

Losing a race is a NORMAL flow for the pujari app (Uber drivers see "ride no
longer available" constantly). Design the UI for it; never retry-loop past a 409.

## Endpoint surface (v1 prefix)

### Auth

**Customer / pujari apps:** `app_context` is selected by the calling app at OTP verify
(`customer` | `pujari`).

**Admin app:** `app_context=admin` is issued **only** if `user_roles` contains `admin` or
`support`. Otherwise **403** at verify — the token is never minted. `require_admin` must
also load `user_roles` from DB (JWT claim alone is insufficient). See SPEC_AMENDMENTS §8, §19.

**Admin login path (`P-ADMIN-AUTH`):** TOTP or email magic-link — **not** SMS OTP
(DLT-blocked; wrong mechanism for an internal console). Admin refresh token TTL ≤ 1 day
(per-`app_context` TTL; customer/pujari keep 30 days). See SPEC_AMENDMENTS §19.

- `POST /v1/auth/otp/request`      {phone} — Redis rate limit: 5/hour per phone.
  Sends OTP via `sms_router` (FAST2SMS → MSG91 failover per `SMS_PROVIDER_ORDER`).
  Response: `{status: "otp_sent", sms_sent: bool, sms_provider: "fast2sms"|"msg91"|null}`.
  **DLT:** Indian providers require DLT registration even for test SMS — delivery may fail
  while API calls succeed. Until DLT approved, use `DEBUG=true` for `otp_dev_only` fallback.
  See SPEC_AMENDMENTS §18.
  OTP stored hashed only; never returned in response. Dev: `DEBUG=true` logs
  `otp_dev_only` in uvicorn when `sms_sent=false`.
- `POST /v1/auth/otp/verify`       {phone, otp, app_context?} -> access + refresh tokens.
  **`app_context` is a JSON body field** (`customer` | `pujari` on SMS path — never a query param).
  **`admin` only via `P-ADMIN-AUTH` (TOTP)** — not SMS OTP. **`admin` only with role** when issued.
  Lockout: increment `otp_verifications.attempts` on every failure (**must persist outside the
  verify transaction** — see `P-AUTH-FIX`); at 5, reject and require a fresh OTP request.
  Additionally Redis rate-limit verify attempts at 10/hour per phone (stops rotation attacks).
- `POST /v1/auth/refresh`          rotate refresh token — lookup session by JWT `jti`, verify
  stored hash with `verify_secret` (not equality on `hash_secret`; see `P-AUTH-FIX`)
- `POST /v1/auth/logout`           revoke session by `jti` + hash verify (`revoked_at`)

### Mobile / shared (public read — no bearer required)

- `GET  /v1/app-config`            launch toggles for Flutter clients (read from
  `platform_settings`). Includes optional **`muhurat_help_contact`** (default active
  relationship manager — name + phone only) for pre-booking muhurat guidance UI. **No auth.** Rate-limit at edge. Response:
  `{ night_bookings_enabled, instant_lead_hours, advance_booking_amount, razorpay_key_id?, payments_enabled, muhurat_help_contact? }`.
  Clients MUST use this (not hardcoded constants) for night-slot UI and instant/advance
  copy. Authoritative gate remains `POST /v1/bookings` (422) and `gate_warnings` on holds.
- `GET  /v1/panchangam`            server-cached daily panchangam (`panchangam_daily`,
  migrations 017–018). **No auth.** Query: `?city=Hyderabad&date=YYYY-MM-DD&locale=te|en`
  (default `date=today` IST, `locale=te`, `panchang_system=drik`). Response:
  `{ city, date, panchang_system: 'drik'|'vakya', locale,
  vaaram, tithi, nakshatram, yoga?,
  rahu_kalam?, yama_gandam?, sunrise, sunset,
  brahma_muhurtam?, amrita_ghadiya?, varjyam?, durmuhurtam?,
  auspicious_windows?: [{label, start, end}], fetched_at, disclaimer }`.
  **Home-ribbon fields (§23.6):** `vaaram` (వారం), `tithi` (తిథి), `nakshatram` (నక్షత్రం),
  `rahu_kalam` (రాహు కాలం), `yama_gandam` (యమగండం, nullable), `sunrise`, `sunset` — all
  locale-aware strings except time windows (ISO 8601 `start`/`end`). Populated by the
  fetch worker from a self-hosted `@ishubhamx/panchangam-js` / telugu-panchangam-app adapter
  (see SPEC_AMENDMENTS §23.6 vendor mapping). Payload is normalized in the worker — clients
  bind to this contract only. **404** when cache row missing (client shows retry; beat backfills).
  **`yama_gandam`:** required in cache rows at worker upsert for Drik launch cities; **nullable**
  in API response (UI shows when present per CUSTOMER.md).
  **Env (server only):** `PANCHANGAM_VENDOR_URL`, `PANCHANGAM_DEFAULT_CITIES` (JSON array, default
  `["Hyderabad"]`), optional `PANCHANGAM_API_KEY`. Populated data requires `P-PANCHANGAM-VENDOR`
  COMPLETED + self-hosted engine running — contract LIVE (`P-PANCHANGAM-API`) ≠ data LIVE.
  Month-marker endpoint (optional v1.1): `GET /v1/panchangam/month?city=&year=&month=`
  → `{ auspicious_dates: ['YYYY-MM-DD', ...] }` derived from cached rows.

### Customer app
- `GET  /v1/service-areas`                     active zones for address dropdown
  (`?city=Hyderabad`); returns `{id, city, zone_name}` — admin-managed (`service_areas`)
- `GET  /v1/addresses`                         list customer addresses (paginated)
- `POST /v1/addresses`                         {line1, city, latitude, longitude,
  service_area_id, ...} — **service_area_id required** (§21.3). MUST set `geom` from
  lat/lng on write (trigger or app; see DATABASE.md migration 005). Checkout requires
  `geom IS NOT NULL` (422 otherwise).
- `PUT  /v1/addresses/{id}`                      update; recompute `geom` when lat/lng change;
  `service_area_id` may be updated
- `GET  /v1/pujas`                             catalog + categories (paginated).
  Each puja summary includes **`is_muhurat_bound`** (§21.8, migration 012) for muhurat
  pill UX. `GET /v1/pujas/{id}` includes the same flag on detail.
- `GET  /v1/checkout/quote?puja_id=&addon_ids[]=`  resolves unit price via
  `pricing_resolver` (SPEC_AMENDMENTS §20.3). **Launch:** no `pujari_id` — broadcast
  pricing only (`pujas.default_price`). Reads `platform_settings.advance_booking_amount`
  from DB and returns `total_amount`, `advance_amount` (live setting), plus both payment options
  (`full_online` and `advance_balance` breakdown per DISPATCH_FLOW.md).
  **Also returns** (SPEC_AMENDMENTS §16): `platform_fee_gross`, `total_charged_online`,
  `tax_statutory_config_id`, `tax_commercial_config_id` — snapshotted at quote.
  Requires `billing_state_code` on user (422 if absent).
  Client UI labels MUST interpolate `advance_amount` — never hardcode ₹250.
- `GET  /v1/pujaris?puja_id=&date=&time=`      browse-only at launch (profiles/ratings);
  **not** used for checkout selection (§21.1). Filter via `pujari_pricing`; verified only
- `POST /v1/slot-holds`                        {date, time} — **no `pujari_id` at launch**
  (broadcast only). 409 if taken. Response:
  `{hold_id, expires_at, pujari_id?, server_time, platform_fee_gross, total_charged_online,
  tax_statutory_config_id, tax_commercial_config_id, billing_state_code,
  advisory_booking_class: 'instant'|'advance'|null, gate_warnings: [{code, message}]}` —
  tax/fee **snapshotted here**; booking inherits, never re-reads current config (§16).
  `gate_warnings` are **advisory** (e.g. `NIGHT_BOOKINGS_DISABLED` when
  `night_bookings_enabled=false` and slot is 00:00–05:59 IST). **`POST /v1/bookings`**
  is authoritative — same slot may still 422 there.
- `POST /v1/bookings`                          {hold_id, puja_id, address_id,
  addon_ids[], promo_code?, payment_mode} —
  `payment_mode`: `'full_online'` | `'advance_balance'` (required). ONE
  transaction: validate hold (`FOR UPDATE`, owner + unexpired, else 410),
  compute and snapshot `total_amount`, `amount_due_online`,
  `amount_due_offline` per DATABASE.md migration 003 rules; insert booking
  status='payment_pending' with `intended_pujari_id = NULL`, `dispatch_mode = 'broadcast'`,
  `hold_id`, `payment_mode` persisted; **INSERT … ON CONFLICT DO NOTHING**
  on `ux_bookings_no_duplicate_submit` (partial unique) so a duplicate never
  aborts the outer transaction — then lookup existing row if no id returned;
  snapshot hold primitives as locals before any write. Snapshot addon prices into
  booking_addons; create
  Razorpay order for **`total_charged_online`** (= `amount_due_online` +
  `platform_fee_gross` from hold snapshot) BEFORE commit (Razorpay
  failure = full rollback); persist `razorpay_order_id` on the booking row
  (migration 004); extend hold to now()+15 min.
  422 if the address has no `geom` (coordinates not geocoded).
  **201** response: `{booking_id, booking_class, razorpay_order_id, amount_due_online,
  amount_due_offline, total_amount, total_charged_online, platform_fee_gross,
  tax_statutory_config_id, tax_commercial_config_id, payment_mode, hold_expires_at}`.
  `booking_class` is **frozen** at insert (§21.6.A) — client uses it for tracking UX
  (instant → active search; advance → calm booked state). **409** idempotent duplicate
  (double-tap / active booking for same slot): same fields plus `"idempotent": true` —
  **same fee and config ids as original**; client opens Razorpay with the returned
  `razorpay_order_id` or navigates to `GET /v1/bookings/{id}`.
- `POST /v1/bookings/{id}/cancel`              caller must be the booking's customer.
  State-gated (see DISPATCH_FLOW.md cancellation table). Refund amount is
  ALWAYS capped at `amount_due_online` — offline balance is never refunded
  via Razorpay. Atomically: cancelled_at + status flip + history row +
  `refunds` row. Returns refund amount + ETA copy.
- `GET  /v1/bookings`                          customer's bookings, cursor-paginated,
  newest first (`status`, `booking_class`, `scheduled_date`, `scheduled_time`,
  `total_amount`, `payment_mode` summary per row)
- `GET  /v1/bookings/{id}`                     status + **`booking_class`** (frozen) +
  payment breakdown (`payment_mode`, `total_amount`, `amount_due_online`,
  `amount_due_offline`, `balance_collected_at`?) + assigned pujari +
  **relationship_manager** (after confirm) + history + refund status if any.
  **Flutter:** after Razorpay SDK success, status may remain `payment_pending` until
  webhook — show **“Confirming payment…”** until `requested` or terminal failure;
  only then show class-appropriate dispatch UX. **No customer phone exposed to pujari
  via this route.**
- `POST /v1/bookings/{id}/dispatch-choice`     **DISABLED at launch (§21.1).** Reserved for
  Phase 2 direct booking. When enabled: `{action: 'broadcast'|'cancel'}` on failed direct
  offer — see DISPATCH_FLOW.md §Direct vs broadcast.
- `WS   /v1/ws/bookings/{id}?ticket=`          **Launch:** `status_changed` events only.
  **No** pujari location relay until Phase 2 (`P-WS`).

### Pujari app
- `POST /v1/pujari/register`                   {bio?, years_experience?} — creates
  `pujaris` row `verification_status='pending'`. Idempotent per user.
- `POST /v1/pujari/kyc/digilocker`             Start Setu DigiLocker (consent row → vendor start).
  Returns `{request_id, url, expires_at}`. Rate-limited. If a live request already
  exists, **200** resumes it (same `request_id` + current vendor `url`) instead of
  minting a second Setu session. **409** only if a live row exists but the vendor
  URL is no longer available.
- `GET  /v1/pujari/kyc/callback`               **PUBLIC** — DigiLocker redirect landing (nonce-bound;
  no bearer). Lightweight: marks `authenticated` or `failed`; redirects to app deep link.
- `GET  /v1/pujari/kyc/requests/{request_id}`  Self-healing poll — re-verifies Setu status,
  drives finalize; returns `{status, scope, doc_types_created[], review_flags[]}`.
- `GET  /v1/pujari/kyc/status`                 `{verification_status, required:[{doc_type, status}]}`.
- `POST /v1/pujari/documents`                  **Selfie only** — presigned PUT to private KYC bucket
  (gating `photo` doc; DigiLocker supplies `identity_proof` + `address_proof`).
- `POST /v1/pujari/documents/{document_id}/confirm`  After presigned PUT — HEAD/S3 fetch, strip JPEG
  EXIF/GPS, set `uploaded_at`. **200** `{document_id, doc_type, status, file_url}`.
  **422** if object missing in S3.
- `POST /v1/pujari/kyc/pan`                    Phase 4 — deferred.
- `POST /v1/me/devices`                        {device_token, platform} — FCM target
  (customer or pujari token). Upsert by `device_token` (globally unique).
- `DELETE /v1/me/devices/{device_token}`         unregister (owner only)
- `GET  /v1/offers`                            live assignments per booking:
  `assignment_id`, `booking_id`, `expires_at`, `puja_name`, `scheduled_date`,
  `scheduled_time`, `area_label` (from address `service_area_id` — **no street**),
  `payment_mode`, `amount_due_offline`. Polled on foreground.
  **Filters:** `responded_at IS NULL`, `expires_at > now()`, **`bookings.cancelled_at IS NULL`**
  (customer-cancelled bookings never appear — pending rows are expired in
  `cancellation_service` on cancel).
  **Dispatch v2 (§21.6.E):** also returns `urgency` (`instant` | `advance`, computed live from
  slot lead vs `instant_lead_hours`) and `urgency_escalated` (bool). Client renders a modal when
  `urgency=='instant'` OR `urgency_escalated`, else an inbox row (§21.6.G). `booking_class`
  (frozen) is informational; `urgency` drives UX. Advance offers may be `is_still_available=false`
  when another pujari already accepted (superseded — §21.6.B).
- `GET  /v1/pujari/bookings`                   assigned pujari's bookings (cursor);
  summary rows for Bookings tab
- `GET  /v1/pujari/bookings/{id}`              assigned pujari only; `status` confirmed+
  required. Returns full service address, `latitude`/`longitude`, static map URL,
  `area_label`, puja/time/money, **relationship_manager** — **no customer phone**.
- `POST /v1/pujari/bookings/{id}/reconfirm`    assigned pujari only (`app_context=pujari`);
  booking must be `confirmed`, advance-class, and have `booking_reconfirmations.ping_sent_at`
  set (T−24h ping delivered). Sets `pujari_confirmed_at = now()` idempotently.
  **200** `{ booking_id, pujari_confirmed_at, already_confirmed: bool }`.
  **409** if not assigned pujari or booking not in reconfirm window.
  **Decline path:** partner uses existing `POST /v1/bookings/{id}/pujari-cancel` (not this route).
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
- `PUT  /v1/me/heartbeat`                      body: `{lat?, lng?}` — **lat/lng optional
  at launch (§21.2).** Always `SET presence:{pujari_id} 1 EX 90` in Redis. When lat/lng
  provided (Phase 2), also writes `pujari_live_location`. App sends every 30s while on duty.
  Partner may go online **without** OS location permission. Go-offline:
  `DELETE /v1/me/heartbeat` (removes key immediately).
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
- `GET  /v1/admin/tax-config/current` — commercial + statutory (read-only) + tax preview (§16)
- `GET  /v1/admin/tax-config/history` — append-only audit, cursor paginated
- `POST /v1/admin/tax-config/commercial` — **only** `platform_fee_gross`,
  `platform_fee_inclusive`, `commission_pct`, `effective_from`, `change_reason`.
  Statutory/legal keys in body → **422**. See `spec/plans/A-TAX-CONFIG.md`.
- KYC review queue (`pujari_documents` pending), `POST /v1/admin/kyc/identity/deny`
  (ban DigiLocker identity hash — audited), booking search + manual
  reassign — MUST use the clear-then-insert flow in DISPATCH_FLOW.md
  ("Manual reassign"): clear `pujari_id` + `intended_pujari_id` with a
  history row, THEN insert the accepted assignment; inserting while the old
  pujari is still set is rejected by Guard 3 by design —, refund override
  (inserts `refunds` row reason='admin_override'), failed-refund queue
  (`refunds.status='failed_permanent'`), promo CRUD, `service_areas` +
  `pujari_service_areas` CRUD, dispute resolution (in_progress -> disputed;
  offline non-payment disputes).
- **Catalogue (Phase 4 — SPEC_AMENDMENTS §19–§20):** admin CRUD for `puja_categories`,
  `pujas`, `puja_addons`, `puja_content_items`; media presign/confirm (`puja_media`);
  `pujari_pricing` per partner; soft-disable only (`is_active`).
  - `GET/POST/PUT /v1/admin/catalog/categories` (+ `PATCH .../reorder`)
  - `GET/POST/PUT /v1/admin/catalog/pujas` (+ `GET .../impact`, `PATCH .../reorder`)
  - `GET/PUT /v1/admin/catalog/pujas/{id}/content` (replace-all per `kind`)
  - `GET/POST /v1/admin/catalog/pujas/{id}/addons`, `PUT /addons/{id}`
  - `GET /v1/admin/catalog/media?entity_type=&entity_id=`
  - `POST /v1/admin/catalog/media/presign` → client `PUT` → `POST .../media/{id}/confirm`
- **Partner directory:** `GET /v1/admin/pujaris` search (phone, name, verification, area).
- **Relationship managers (§21.4):** `GET/POST/PUT /v1/admin/relationship-managers` —
  CRUD RM rows (name, phone, `is_active`, optional `city`). Assign default RM per city in
  `platform_settings` or per booking (`bookings.relationship_manager_id`, migration 012).
- **Booking detail:** `GET /v1/admin/bookings/{id}` — 360° view for ops.
- **Money read-only (pre–Phase 3):** `GET /v1/admin/bookings/{id}/money` — payments +
  refunds; label **"Collected online — settlement pending"** (never "earnings" until splits).

## Transition authorization matrix (enforce in the auth dependency + handlers)

Guards in the "Required state" column are necessary but not sufficient — handlers must
also use guarded `UPDATE … WHERE <predicates>`; 0 rows → 409 `StaleBookingState`.

| Endpoint | Who may call | Required state |
|---|---|---|
| `/bookings/{id}/cancel` | booking's customer (`app_context=customer`) | payment_pending / requested / confirmed |
| `/bookings/{id}/pujari-cancel` | assigned pujari (`app_context=pujari`) | confirmed only (not in_progress) |
| `/pujari/bookings/{id}/reconfirm` | assigned pujari (`app_context=pujari`) | confirmed; reconfirm ping sent; not yet `pujari_confirmed_at` |
| `/offers/{aid}/accept`, `/reject` | assignment's pujari (`app_context=pujari`) | offer live (unexpired, unresponded) |
| `/pujari/bookings`, `/pujari/bookings/{id}` | assigned pujari (`app_context=pujari`) | confirmed+ for detail |
| `/bookings/{id}/start` | assigned pujari | confirmed, within ±60 min of scheduled_time |
| `/bookings/{id}/confirm-balance-collected` | assigned pujari | in_progress or confirmed; advance_balance with balance due |
| `/bookings/{id}/complete` | assigned pujari | in_progress; balance acknowledged if due |
| `/bookings/{id}/dispatch-choice` | booking's customer | **DISABLED at launch** — Phase 2 direct only |
| manual reassign / refund override / dispute | admin role | any (audited) |

## OpenAPI — mobile client contract

- FastAPI exposes **`GET /openapi.json`** when `DEBUG=true` (see `app/main.py`).
- **Ship artifact:** export `spec/openapi.json` (or `mobile/openapi.json` in the Flutter
  repo) on every API-contract change; Flutter generates Dio client via `openapi_generator`.
- Do not hand-maintain duplicate request/response types in the mobile repo.

## Dispatch service (internal, not an endpoint)

`broadcast_booking(booking_id)` / `rebroadcast_booking(booking_id, fresh=False)`:
**Launch:** time-based `dispatch_starts_at` / `dispatch_deadline` (§21.6). **Phase 2:**
round/radius schedule (3/6/10/15 km, max 4). `fresh=True` dispatch-state reset
(pujari-cancel re-dispatch), idempotency (Redis dispatch lock + compare-and-set),
FCM retry + `sms_router` SMS fallback, exhaustion (`failed_no_pujari` + auto-refund)
— all normative in DISPATCH_FLOW.md; do not re-derive values here.
