# Admin portal — backend track

Tasks trace to `spec/API_CONTRACTS.md` §Admin and DISPATCH_FLOW.md admin flows.

---

## Settings

### A-ADVANCE — Advance booking amount
- **Spec:** API_CONTRACTS.md
- **Status:** DONE
- **Files:** `app/api/v1/endpoints/admin.py`

### A-COMMISSION — Platform fee + GST settings
- **Spec:** SPEC_AMENDMENTS.md §16; DATABASE.md `platform_settings`
- **Status:** TODO (blocked on P-GST-MODEL for rate semantics)
- **Acceptance:** `GET/PUT /v1/admin/settings/commission` and `/gst` (or combined) —
  `commission_pct`, `gst_pct` in `platform_settings`, same dynamic pattern as A-ADVANCE
- **Depends on:** P-GST-MODEL, P-SPLIT-CONFIG

### A-AREAS — Service areas
- **Spec:** API_CONTRACTS.md
- **Status:** TODO
- **Acceptance:** CRUD `service_areas`, assign `pujari_service_areas`

### A-PROMO — Promo CRUD
- **Spec:** API_CONTRACTS.md
- **Status:** TODO

---

## Supply quality (Phase 0.5 — move early)

### A-KYC — KYC review queue
- **Spec:** API_CONTRACTS.md §Admin KYC
- **Status:** TODO
- **Acceptance:**
  - `GET /v1/admin/kyc/pending` — pending `pujari_documents`
  - `POST /v1/admin/kyc/{doc_id}/approve|reject` — flip `pujaris.verification_status`
  - Signed URLs for private bucket docs only
- **Depends on:** B-KYC
- **Priority:** Phase 0.5 — cannot onboard real supply without this

---

## Operations

### A-SEARCH — Booking search
- **Spec:** API_CONTRACTS.md
- **Status:** TODO
- **Acceptance:** Search by phone, booking id, date range, status

### A-REASSIGN — Manual reassign
- **Spec:** DISPATCH_FLOW.md §Manual reassign
- **Status:** TODO
- **Acceptance:** Clear-then-insert in ONE transaction:
  1. `pujari_id = NULL`, `intended_pujari_id = NULL` + history
  2. INSERT accepted assignment for new pujari
- **Verify:** DISPATCH_FLOW launch-gate test

### A-REFUND — Refund ops
- **Spec:** API_CONTRACTS.md
- **Status:** TODO
- **Acceptance:**
  - `POST /v1/admin/refunds/override` — insert `refunds` reason=`admin_override` (never inline Razorpay)
  - `GET /v1/admin/refunds?status=failed_permanent`
- **Depends on:** P-REFUND-CAP

### A-DISPUTE — Dispute resolution
- **Spec:** API_CONTRACTS.md, DISPATCH_FLOW.md disputed state
- **Status:** TODO
- **Acceptance:** `in_progress` → `disputed`; offline non-payment cases; no Razorpay refund for offline portion

---

## Auth

### A-ADMIN-ROLE — Role enforcement
- **Spec:** SPEC_AMENDMENTS.md; API_CONTRACTS.md
- **Status:** TODO
- **Depends on:** P-ADMIN-ROLE
- **Acceptance:** Admin tokens only for users with `user_roles` admin/support

---

## Admin track exit gate

- [ ] Approve pujari end-to-end
- [ ] Change advance amount → next quote reflects it
- [ ] Find booking + manual reassign
- [ ] Resolve one `failed_permanent` refund
