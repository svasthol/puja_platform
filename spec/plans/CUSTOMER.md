# Customer app — backend track

Tasks trace to `spec/API_CONTRACTS.md` §Customer app unless marked SPEC_AMENDMENTS.

> **Status lives in `STATUS.md` — the single source of truth for implementation progress.**
> Track files define scope only: Spec / Files / Acceptance / Depends-on. Never add a
> `Status:` field here; it will drift.

**Launch policy:** `spec/plans/LAUNCH_POLICY.md`, `SPEC_AMENDMENTS.md` §21.

> **Flutter client:** `C-FLUTTER-CUSTOMER` — **IN_PROGRESS** in `STATUS.md` (sub-track:
> shell **COMPLETED**, panchangam **IN_PROGRESS**, catalogue **IN_PROGRESS**). This file tracks
> **backend APIs only**; launch §21 customer endpoints are **COMPLETED** in this repo.
> Catalogue sync matrix (admin ↔ customer ↔ partner): `spec/plans/CATALOG_SYNC.md`.

---

## Discovery and checkout

### C-PUJAS — Catalog list
- **Spec:** API_CONTRACTS.md `GET /v1/pujas`
- **Files:** `app/api/v1/endpoints/catalog.py`
- **Acceptance:** Cursor pagination `?cursor=&limit=20`, real `next_cursor`
- **Depends on:** C-PAGINATION pattern

### C-PUJARIS — Browse pujaris (launch: not checkout selection)
- **Spec:** API_CONTRACTS.md `GET /v1/pujaris`
- **Launch:** Profiles/ratings browse only — **no direct booking** at checkout (§21.1)
- **Files:** `app/api/v1/endpoints/catalog.py`

### C-SERVICE-AREAS — Area dropdown
- **Spec:** API_CONTRACTS.md `GET /v1/service-areas`
- **Acceptance:** Active `service_areas` for city; mandatory on address create

### C-QUOTE — Checkout quote
- **Spec:** API_CONTRACTS.md, DISPATCH_FLOW.md, SPEC_AMENDMENTS §16
- **Launch:** Broadcast pricing only (`pujas.default_price`) — no `pujari_id` on quote
- **Product:** Present `full_online` first in client UI (MASTER.md product policy)

### C-HOLD — Slot holds
- **Spec:** API_CONTRACTS.md `POST /v1/slot-holds`, §16
- **Launch:** **No `pujari_id`** — broadcast only

### C-ADDR — Customer addresses + billing state
- **Spec:** API_CONTRACTS.md §Addresses; SPEC_AMENDMENTS §16, §21.3
- **Acceptance:**
  - `POST/GET/PUT /v1/addresses` with lat/lng → `geom` via trigger
  - **`service_area_id` required** (mandatory dropdown)
  - `users.billing_state_code`; 422 if missing at quote
- **Blocks:** P-IGST

### C-BOOK — Create booking
- **Spec:** API_CONTRACTS.md, IDEMPOTENT_BOOKING.md, §16, §21.6.A
- **Launch:** Always `dispatch_mode='broadcast'`, `intended_pujari_id=NULL` at insert
- **Dispatch v2 (§21.6.A):** this endpoint is the **single authoritative gate**. It freezes
  `booking_class` (`instant`/`advance`) from lead time and applies the night gate **before** the
  Razorpay order: instant + night slot (00:00–05:59 IST) → **422 `INSTANT_NIGHT_BLOCKED`**; any night
  slot at launch → **422 `NIGHT_BOOKINGS_DISABLED`** (2a). `POST /v1/slot-holds` may pre-warn in the UI,
  but the 422 here is authoritative — surface it as a clear "night bookings aren't available yet" message.
- After payment, dispatch is **immediate** (§21.6.C); the booking sits in `requested` ("Finding your
  pujari…") until a pujari accepts (`confirmed`) or the `slot − 3h` backstop refunds it.

### C-PROMO — Promo code redemption
- **Spec:** API_CONTRACTS.md checkout; promo redemption in booking transaction
- **Files:** `app/services/booking_service.py` — remove `promo_pct = 0` hardcode
- **Acceptance:** Validate + redeem atomically (counter upsert in checkout txn); over-limit → 422

---

## Post-booking

### C-CANCEL — Customer cancel
- **Spec:** API_CONTRACTS.md, DISPATCH_FLOW.md cancellation table
- **Files:** `app/services/cancellation_service.py`
- **Acceptance:** One txn — `cancelled_at`, status `cancelled`, history, refund row when
  applicable; pending partner assignments → `expired` + `responded_at` (same txn).
- **Flutter (`C-FLUTTER-CANCEL` — COMPLETED 2026-08-09):** Detail screen status-aware
  cancel dialog → `POST /v1/bookings/{id}/cancel` → refund snackbar → pop + refresh list.
  Files: `customer_booking_detail_screen.dart`, `customer_cancel_eligibility.dart`.

### C-GET — Booking detail
- **Spec:** API_CONTRACTS.md `GET /v1/bookings/{id}`
- **Launch:** After confirm — assigned pujari name + **relationship_manager** block.
  **No pujari direct phone.** Status, payment, history, refund.
- **Flutter (§23):** Response includes frozen **`booking_class`** for tracking UX.
  After Razorpay SDK success, handle **`payment_pending`** limbo until webhook flips
  to `requested` — do not show “finding priest” radar until then.

### C-APP-CONFIG — Launch toggles (read-only)
- **Spec:** API_CONTRACTS.md `GET /v1/app-config` (public)
- **Acceptance:** Returns `night_bookings_enabled`, `instant_lead_hours`, `advance_booking_amount`
  from `platform_settings` — clients must not hardcode night-slot rules.

### C-PANCHANGAM — Panchangam read (server cache)
- **Spec:** API_CONTRACTS.md `GET /v1/panchangam`; SPEC_AMENDMENTS §23.6, §23.6.1
- **Launch (`C-PANCHANGAM-UI`):** Home ribbon binds to normalized API response only;
  show `panchang_system` (Drik/Vakya); disclaimer footer + **"Drik Panchangam"** label.
  Display home-ribbon fields: `date`, `vaaram`, `tithi`, `nakshatram`, `rahu_kalam`,
  `yama_gandam` (when present), `sunrise`, `sunset` — all from `GET /v1/panchangam`
  (never vendor APIs). **404 → retry UI**; never crash.
- **HOLD (Aug 2026):** Flutter ribbon code exists in `mana_guruji_mobile` — **IN_PROGRESS**
  under `C-FLUTTER-PANCHANGAM`; device-QA vs design 01 before marking COMPLETED.
- **Post-launch (`C-PANCHANGAM-CALENDAR`):** Full calendar tab (design screen 04) deferred —
  needs `GET /v1/panchangam/month` (v1.1), wider cache horizon, and auspicious-date rule.

### C-LIST — Booking history
- **Spec:** API_CONTRACTS.md `GET /v1/bookings` (v3.2); SPEC_AMENDMENTS.md §1
- **Files:** `app/api/v1/endpoints/bookings.py`
- **Acceptance:** Cursor list for customer's bookings, newest first

### C-DISPATCH-CHOICE — Direct miss prompt
- **Launch:** **DISABLED** (§21.1). Reserved for Phase 2 direct booking.

---

## Realtime

### C-WS — WebSocket
- **Spec:** API_CONTRACTS.md §WS; ARCHITECTURE.md rule 6
- **Launch:** `status_changed` only — **no** pujari location relay (Phase 2 `P-WS`)

### C-DEVICE — FCM device token (customer)
- **Spec:** API_CONTRACTS.md §Devices
- **Files:** `app/api/v1/endpoints/devices.py`
- **Acceptance:** `POST /v1/me/devices` registers token for push notifications

### C-PAGINATION — Shared pagination helper
- **Spec:** API_CONTRACTS.md intro
- **Files:** `app/schemas/common.py`, apply to all list endpoints

---

## Customer track exit gate

**Backend (this repo):** API items above marked COMPLETED in `STATUS.md` meet launch §21.

**Flutter (`C-FLUTTER-CUSTOMER` — IN_PROGRESS):**

- [x] Browse catalogue — categories, list, detail (`C-FLUTTER-CATALOG`; checkout CTA stub)
- [ ] Pick area + pin address → hold (broadcast) → pay → track booking
- [ ] While `requested`: "Finding your pujari…" UX (immediate dispatch on payment, §21.6.C)
- [ ] Night slot (00:00–05:59) → clear "not available yet" message on the 422 (§21.6.A); read `GET /v1/app-config` + `gate_warnings` on holds — blocks **all** night slots at launch, not instant-only
- [ ] After Razorpay success → `payment_pending` "Confirming payment…" until `requested`
- [ ] Tracking UX branches on **`booking_class`** (instant radar vs advance calm state)
- [ ] After confirm: pujari name + RM — no direct phone
- [ ] Address CRUD with mandatory `service_area_id`
- [ ] Booking list + full detail
- [ ] Idempotent double-submit returns 409 + same `razorpay_order_id`
- [ ] `advance_balance` refund copy states offline portion not refunded via platform
