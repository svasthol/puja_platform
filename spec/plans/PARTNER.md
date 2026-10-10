# Partner (pujari) app — backend track

Tasks trace to `spec/API_CONTRACTS.md` §Pujari app unless marked SPEC_AMENDMENTS.

> **Status lives in `STATUS.md` — the single source of truth for implementation progress.**
> Track files define scope only: Spec / Files / Acceptance / Depends-on. Never add a
> `Status:` field here; it will drift.

**Launch policy:** `spec/plans/LAUNCH_POLICY.md`, `SPEC_AMENDMENTS.md` §21.

> **Flutter client:** `P-FLUTTER-PARTNER` / `C-LAUNCH-UX` — **IN_PROGRESS** in `STATUS.md`
> (not started; separate repo). This file tracks **backend APIs only**; launch §21 partner
> endpoints (`B-OFFERS`, `B-BOOKINGS`, `B-HEARTBEAT`, etc.) are **COMPLETED** in this repo.

---

## Phase 0.5 — Supply onboarding (parallel with dispatch)

### B-REGISTER — Pujari profile bootstrap
- **Spec:** SPEC_AMENDMENTS.md §5; API_CONTRACTS.md
- **Files:** `app/api/v1/endpoints/partner_onboarding.py`
- **Acceptance:** `POST /v1/pujari/register` creates `pujaris` row `verification_status='pending'` (idempotent)
- **Verify:** Cannot receive offers until `verified` (admin KYC)
- **On verify:** `ensure_partner_dispatch_readiness()` links active service areas, default
  weekly hours, and active-puja pricing (until partner availability UI ships — `B-AVAIL` HOLD)

### B-KYC — DigiLocker vendor KYC + camera selfie
- **Spec:** API_CONTRACTS.md; migration **020**; vendor-agnostic `KycVendor` Protocol
- **Flow:** consent row → Setu DigiLocker start → public nonce callback (fast-path) →
  self-healing poll finalize → `pujari_documents` pending → A-KYC approve
- **Acceptance:** DigiLocker supplies `identity_proof` + `address_proof`; partner uploads
  gating `photo` selfie via presigned PUT; admin approves via A-KYC
- **Depends on:** B-REGISTER; S3 `S3_BUCKET_KYC`; Setu sandbox creds for E2E
- **Note:** A-KYC is downstream reviewer only — not a dependency

### B-DEVICE — FCM device token
- **Spec:** SPEC_AMENDMENTS.md; ARCHITECTURE.md FCM; API_CONTRACTS.md §Devices
- **Files:** `app/api/v1/endpoints/devices.py`
- **Acceptance:** `POST /v1/me/devices` {device_token, platform} → `devices` table; `DELETE` owner-only; upsert on conflict

---

## Go online

### B-HEARTBEAT — Presence (launch: no GPS required)
- **Spec:** API_CONTRACTS.md, DISPATCH_FLOW.md §Presence, §21.2
- **Files:** `app/api/v1/endpoints/pujaris.py`
- **Launch:** `PUT /heartbeat` sets Redis presence; `{lat,lng}` **optional**. Partner may
  go online without OS location permission. Poll `GET /v1/offers` every 3–5s while on duty.
- **Phase 2:** optional lat/lng on heartbeat for geo dispatch

### B-AVAIL — Weekly availability
- **Spec:** API_CONTRACTS.md `PUT /v1/me/availability`
- **Files:** `app/api/v1/endpoints/pujaris.py`
- **Acceptance:** CRUD `pujari_availability` windows

### B-UNAVAIL — Date blocks
- **Spec:** API_CONTRACTS.md `PUT /v1/me/unavailability`
- **Acceptance:** CRUD `pujari_unavailability`; dispatch excludes those dates

---

## Offer inbox + bookings (launch UX)

> **Normative UX (do not change):** pre-accept broadcast jobs appear **only** in the
> **Offers** tab / instant modal (`GET /v1/offers`). The **Bookings** tab lists
> **post-accept** assigned work (`GET /v1/pujari/bookings`) — never merge pre-accept offers
> into Bookings.

### B-OFFERS — List live offers
- **Spec:** API_CONTRACTS.md
- **Launch:** Each offer shows puja, date/time, money, **area_label only** — no customer
  address or phone. FCM additive; poll on Offers tab.
- **Dual UX (Dispatch v2, §21.6.E):** each offer carries a computed `urgency` (`instant` | `advance`)
  and `urgency_escalated` flag. Render a **Rapido-style accept/reject modal** when
  `urgency == 'instant'` OR `urgency_escalated == true`; otherwise show the offer as an **inbox row**
  in the Offers tab. Never assume a modal is always push-triggered — an advance booking that crossed
  the instant threshold surfaces its modal on the next **poll** (the flip FCM only reaches pujaris who
  already held the offer).
- **FCM types (§21.6.H):** `offer_instant` (high priority → modal), `offer_advance` (normal → inbox),
  `accept_ack` (advance only, on accept: "Added to your Bookings — we'll confirm ~24h before").
- **Accept-contention (§21.6.G):** advance offers are broadcast to the whole eligible pool and live up
  to 24h, so an offer someone else already took will 409 on accept — expected launch behaviour, not a bug.
  Show live "still available?" state on inbox rows and handle 409 gracefully. Once one pujari accepts, the
  other offers are **superseded** and disappear from the inbox (§21.6.B). Live advance offers per pujari
  are capped (`max_live_advance_offers_per_pujari`, default 15).

### B-BOOKINGS — Assigned booking list + detail
- **Spec:** API_CONTRACTS.md `GET /v1/pujari/bookings`, `GET /v1/pujari/bookings/{id}`
- **Launch:** Bookings tab — list confirmed/upcoming/past. Detail after confirm: full address,
  static map link, RM contact — **no customer phone**. Calendar UI Phase 2.

### B-ACCEPT — Accept race
- **Spec:** API_CONTRACTS.md, DISPATCH_FLOW.md accept
- **Launch:** Soft travel-buffer check at accept (§21.5) — 409 with distinct copy
- **UX:** Handle 409/410 without retry loops

### B-REJECT — Reject offer
- **Spec:** API_CONTRACTS.md, DISPATCH_FLOW.md fast path
- **Depends on:** P-REJECT-FAST
- **Note:** Rejectors are **never** re-offered same booking (§21.6)

---

## Service execution

### B-START — Start service
- **Spec:** API_CONTRACTS.md transition matrix
- **Window:** ±60 min of `scheduled_time` Asia/Kolkata (stricter for `is_muhurat_bound` — Phase 2 UX)

### B-BALANCE — Offline balance acknowledgement
- **Spec:** API_CONTRACTS.md, DISPATCH_FLOW.md advance_balance

### B-COMPLETE — Complete service
- **Spec:** API_CONTRACTS.md

### B-EARNINGS — Earnings screen
- **Spec:** API_CONTRACTS.md `GET /v1/me/earnings`
- **Blocked-by:** P-SPLITS (Phase 3)
- **Acceptance:** `platform_payout` from `payment_splits` + `direct_collection` from `amount_due_offline` where `balance_collected_at` set

### B-TAX-PROFILE — Entity type + PAN on file (launch prep)
- **Spec:** API_CONTRACTS.md `GET/PUT /v1/me/tax-profile`; `POST /v1/pujari/kyc/pan`
- **Files:** `app/api/v1/endpoints/pujaris.py`, `partner_onboarding.py`, `app/services/pujari_compliance.py`
- **Acceptance:** Partner can set `entity_type` + PAN; optional accept gates: `PAN_ACCEPT_GATE_ENABLED`, `PUJARI_TAX_PROFILE_REQUIRED_FOR_ACCEPT` (default false)
- **Flutter:** `P-FLUTTER-PAN-PROFILE`, KYC hub step — COMPLETED in `STATUS.md`

### B-TAX-SUMMARY — FY facilitation read-only
- **Spec:** API_CONTRACTS.md `GET /v1/me/tax-summary`; **`spec/plans/PAN_FY_GATES.md`** (₹4.5L warn / ₹5L block without PAN)
- **Acceptance:** FY gross + TDS lines for partner transparency while accrual OFF/shadow; no withholding UI
- **Flutter:** `P-FLUTTER-TAX-SUMMARY` — COMPLETED in `STATUS.md`

---

## Phase 5 — Provider dropout (SPEC_AMENDMENTS)

### B-CANCEL — Pujari cancel assigned booking
- **Spec:** SPEC_AMENDMENTS.md §3; API_CONTRACTS.md
- **Acceptance:** Assigned pujari can cancel `confirmed` booking; triggers customer refund per policy + reliability signal; enqueue re-dispatch or admin alert
- **Launch:** Required for advance scheduling + mandatory reconfirmation (§21.7).
  **Reconfirm screen "No":** routes here — confirm dialog before call.
- **Flutter (`P-FLUTTER-PUJARI-CANCEL` — COMPLETED 2026-08-09):** Detail + reconfirm card
  → `POST /v1/bookings/{id}/pujari-cancel` → pop detail → **Requests tab** + `refreshFromPush()`
  on offers. Files: `partner_booking_detail_screen.dart`, `partner_cancel_eligibility.dart`,
  `partner_shell_intent.dart`.

### B-OFFERS-LIST — Partner inbox excludes cancelled bookings
- **Spec:** DISPATCH_FLOW.md §Cancellation; API_CONTRACTS.md `GET /v1/offers`
- **Files:** `app/api/v1/endpoints/offers.py`, `app/services/cancellation_service.py`
- **Acceptance:** After customer cancel, `GET /v1/offers` returns no rows for that booking;
  accept on stale assignment → 410. Test: `tests/test_launch_slice.py::test_list_offers_excludes_customer_cancelled_booking`.
- **Flutter:** 410 accept → `refreshFromPush()` (`offers_controller.dart`). **`P-FCM-CUSTOMER-CANCEL` COMPLETED** — `offer_withdrawn` push dismisses instant modal + refreshes inbox.

### B-RECONFIRM — Partner attendance ack (§23)
- **Spec:** API_CONTRACTS.md `POST /v1/pujari/bookings/{id}/reconfirm`
- **Acceptance:** Idempotent `pujari_confirmed_at`; only after ping sent; 409 when not eligible
- **Depends on:** P-RECONFIRM (worker ping), P-RECONFIRM-API (endpoint)

---

## Partner track exit gate

**Backend (this repo):** API items above marked COMPLETED in `STATUS.md` meet launch §21.

**Flutter (`P-FLUTTER-PARTNER` — IN_PROGRESS):**

- [x] OTP login, go online (heartbeat, no GPS), Offers + Bookings tabs, l10n EN/TE
- [x] Receive offer (**FCM-primary** for `offer_instant`; 20s poll safety net) — inbox + modal
- [x] Accept / reject → 409/410 UX; **410 → refresh inbox** (customer-cancel stale card)
- [x] Bookings list + detail + lifecycle + reconfirm + **pujari-cancel** → Requests tab
- [x] FCM handlers (`offer_instant`, `offer_advance`, `reconfirm_*`, `accept_ack`); sound device QA pending (`P-FLUTTER-FCM-SOUND`)
- [x] **COMPLETED:** `P-FCM-CUSTOMER-CANCEL` — partner push when customer cancels (`offer_withdrawn`)
- [x] Register → KYC approved → online (`P-FLUTTER-REGISTER` / `P-FLUTTER-KYC` — 2026-08-30)
- [x] PAN profile + FY tax summary (`P-FLUTTER-PAN-PROFILE`, `P-FLUTTER-TAX-SUMMARY` — 2026-09-14)
- [ ] Set availability UI (`P-FLUTTER-AVAILABILITY` PENDING — backend ready)
- [ ] Earnings row visible after P-SPLITS (`P-FLUTTER-EARNINGS-UI` HOLD)
- [x] Reject triggers rebroadcast per §21.6 (backend + client refresh)
