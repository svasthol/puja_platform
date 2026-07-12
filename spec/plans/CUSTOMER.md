# Customer app — backend track

Tasks trace to `spec/API_CONTRACTS.md` §Customer app unless marked SPEC_AMENDMENTS.

---

## Discovery and checkout

### C-PUJAS — Catalog list
- **Spec:** API_CONTRACTS.md `GET /v1/pujas`
- **Status:** PARTIAL
- **Files:** `app/api/v1/endpoints/catalog.py`
- **Acceptance:** Cursor pagination `?cursor=&limit=20`, real `next_cursor`
- **Depends on:** C-PAGINATION pattern

### C-QUOTE — Checkout quote
- **Spec:** API_CONTRACTS.md, DISPATCH_FLOW.md payment models
- **Status:** DONE
- **Files:** `app/api/v1/endpoints/bookings.py`
- **Product:** Present `full_online` first in client UI (MASTER.md product policy)

### C-PUJARIS — Available pujaris
- **Spec:** API_CONTRACTS.md `GET /v1/pujaris`
- **Status:** PARTIAL
- **Files:** `app/api/v1/endpoints/catalog.py`
- **Acceptance:** Filter via `pujari_pricing` for `puja_id`; cursor pagination; verified only
- **Depends on:** P-DISP-PRICING query pattern

### C-HOLD — Slot holds
- **Spec:** API_CONTRACTS.md `POST /v1/slot-holds`
- **Status:** DONE

### C-ADDR — Customer addresses
- **Spec:** API_CONTRACTS.md §Addresses (v3.2); DATABASE.md geo conventions
- **Status:** TODO
- **Files:** `app/api/v1/endpoints/addresses.py` (new)
- **Acceptance:**
  - `POST/GET/PUT /v1/addresses` with `latitude`, `longitude`
  - **Always** set `geom = ST_SetSRID(ST_MakePoint(lng, lat), 4326)::geography` on write (trigger or app)
  - Checkout 422 if `geom IS NULL` (already enforced in `booking_service.py`)
- **Verify:** Create address → book → dispatch geo query returns candidates

### C-BOOK — Create booking
- **Spec:** API_CONTRACTS.md, IDEMPOTENT_BOOKING.md
- **Status:** DONE
- **Files:** `app/services/booking_service.py`

### C-PROMO — Promo codes
- **Spec:** API_CONTRACTS.md, DISPATCH_FLOW.md race matrix
- **Status:** TODO
- **Files:** `app/services/booking_service.py` — remove `promo_pct = 0` hardcode
- **Acceptance:** Validate + redeem atomically; over-limit → 422

---

## Post-booking

### C-CANCEL — Customer cancel
- **Spec:** API_CONTRACTS.md, DISPATCH_FLOW.md cancellation table
- **Status:** DONE
- **Files:** `app/services/cancellation_service.py`

### C-GET — Booking detail
- **Spec:** API_CONTRACTS.md `GET /v1/bookings/{id}`
- **Status:** PARTIAL
- **Acceptance:** status, payment breakdown, assigned pujari profile, `booking_status_history`, refund status if any

### C-LIST — Booking history
- **Spec:** API_CONTRACTS.md `GET /v1/bookings` (v3.2); SPEC_AMENDMENTS.md §1
- **Status:** TODO
- **Files:** `app/api/v1/endpoints/bookings.py`
- **Acceptance:** Cursor list for customer's bookings, newest first

### C-DISPATCH-CHOICE — Direct miss prompt
- **Spec:** API_CONTRACTS.md, DISPATCH_FLOW.md direct mode
- **Status:** PARTIAL (endpoint exists; P-DISP-CHOICE not wired)

---

## Realtime

### C-WS — WebSocket tracking
- **Spec:** API_CONTRACTS.md §WS
- **Status:** PARTIAL
- **Next:** Receive server-published status + pujari location events (P-WS)

### C-PAGINATION — Shared pagination helper
- **Spec:** API_CONTRACTS.md intro
- **Status:** TODO
- **Files:** `app/schemas/common.py`, apply to all list endpoints

---

## Customer track exit gate

- [ ] Browse → hold (direct or any) → pay → track booking
- [ ] Address CRUD without manual script
- [ ] Booking list + full detail
- [ ] Idempotent double-submit returns 409 + same `razorpay_order_id`
- [ ] `advance_balance` refund copy states offline portion not refunded via platform
