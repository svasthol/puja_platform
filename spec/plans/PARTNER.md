# Partner (pujari) app — backend track

Tasks trace to `spec/API_CONTRACTS.md` §Pujari app unless marked SPEC_AMENDMENTS.

---

## Phase 0.5 — Supply onboarding (parallel with dispatch)

### B-REGISTER — Pujari profile bootstrap
- **Spec:** SPEC_AMENDMENTS.md §5; API_CONTRACTS.md
- **Status:** TODO
- **Files:** `app/api/v1/endpoints/pujaris.py` or `partner_onboarding.py`
- **Acceptance:** `POST /v1/pujari/register` creates `pujaris` row `verification_status='pending'`
- **Verify:** Cannot receive offers until `verified` (admin KYC)

### B-KYC — Document upload
- **Spec:** API_CONTRACTS.md admin KYC; ARCHITECTURE.md S3 private bucket
- **Status:** TODO
- **Acceptance:** Signed upload URL → `pujari_documents` row; admin approves via A-KYC
- **Depends on:** A-KYC

### B-DEVICE — FCM device token
- **Spec:** SPEC_AMENDMENTS.md; ARCHITECTURE.md FCM
- **Status:** TODO
- **Acceptance:** `POST /v1/me/devices` {device_token, platform} → `devices` table

---

## Go online

### B-HEARTBEAT — Presence + location
- **Spec:** API_CONTRACTS.md, DISPATCH_FLOW.md §Presence
- **Status:** DONE
- **Files:** `app/api/v1/endpoints/pujaris.py`
- **Note:** `geom` set correctly on heartbeat; poll `GET /v1/offers` every 3–5s while on duty

### B-AVAIL — Weekly availability
- **Spec:** API_CONTRACTS.md `PUT /v1/me/availability`
- **Status:** TODO
- **Files:** `app/api/v1/endpoints/pujaris.py`
- **Acceptance:** CRUD `pujari_availability` windows

### B-UNAVAIL — Date blocks
- **Spec:** API_CONTRACTS.md `PUT /v1/me/unavailability`
- **Status:** TODO
- **Acceptance:** CRUD `pujari_unavailability`; dispatch excludes those dates

---

## Offer inbox (Rapido-style)

### B-OFFERS — List live offers
- **Spec:** API_CONTRACTS.md
- **Status:** DONE
- **Product:** Poll every 3–5s during active dispatch; FCM is additive

### B-ACCEPT — Accept race
- **Spec:** API_CONTRACTS.md, DISPATCH_FLOW.md accept
- **Status:** DONE
- **UX:** Handle 409/410 without retry loops

### B-REJECT — Reject offer
- **Spec:** API_CONTRACTS.md, DISPATCH_FLOW.md fast path
- **Status:** PARTIAL
- **Depends on:** P-REJECT-FAST

---

## Service execution

### B-START — Start service
- **Spec:** API_CONTRACTS.md transition matrix
- **Status:** DONE
- **Window:** ±60 min of `scheduled_time` Asia/Kolkata

### B-BALANCE — Offline balance acknowledgement
- **Spec:** API_CONTRACTS.md, DISPATCH_FLOW.md advance_balance
- **Status:** DONE

### B-COMPLETE — Complete service
- **Spec:** API_CONTRACTS.md
- **Status:** DONE

### B-EARNINGS — Earnings screen
- **Spec:** API_CONTRACTS.md `GET /v1/me/earnings`
- **Status:** BLOCKED on P-SPLITS
- **Acceptance:** `platform_payout` from `payment_splits` + `direct_collection` from `amount_due_offline` where `balance_collected_at` set

---

## Phase 5 — Provider dropout (SPEC_AMENDMENTS)

### B-CANCEL — Pujari cancel assigned booking
- **Spec:** SPEC_AMENDMENTS.md §3; API_CONTRACTS.md
- **Status:** TODO
- **Acceptance:** Assigned pujari can cancel `confirmed` booking; triggers customer refund per policy + reliability signal; enqueue re-dispatch or admin alert
- **Launch:** Required for bookings scheduled &gt;24h ahead; optional for same-day-only MVP

---

## Partner track exit gate

- [ ] Register → KYC approved → set availability → heartbeat
- [ ] Receive offer (push + poll) → accept → start → complete
- [ ] Earnings row visible after P-SPLITS
- [ ] Reject triggers instant rebroadcast (P-REJECT-FAST)
