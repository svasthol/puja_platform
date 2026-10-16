# Puja MVP launch policy (geo, dispatch, contact)

**Status:** Approved product policy (July 2026). **Dispatch v2 (§21.6.A–H) folded in.**  
**Canonical amendment:** `SPEC_AMENDMENTS.md` §21 (+ §21.6.A–H Dispatch v2).  
**Behavioural detail:** `DISPATCH_FLOW.md` §Puja MVP launch dispatch + §Dispatch windows + §Dispatch v2 beat tasks.  
**API surface:** `API_CONTRACTS.md` §Launch policy.

This document is the **human-readable summary** for ops and product. Implementers
follow the amendment + dispatch flow + API contracts.

---

## Launch (ship now)

| Area | Policy |
|------|--------|
| **Dispatch mode** | **Broadcast only** — customer never picks a pujari at checkout |
| **Matching** | All **eligible online** verified pujaris in the **launch city** (Hyderabad); **no GPS radius** |
| **Area label** | Customer **must** pick a `service_areas` zone (dropdown); shown on offer card **only** (display) |
| **Customer address** | Map pin required (`addresses.geom`); full address hidden from pujari until **confirmed** |
| **Pujari presence** | Online/offline via heartbeat **without GPS** |
| **Availability** | Weekly windows + date blocks — unchanged |
| **Overlap (hard)** | DB `ex_bookings_pujari_no_overlap` — true time overlap forbidden |
| **Buffer (soft)** | Default **60 min** after puja duration — eligibility + accept-time check only |
| **Dispatch timing** | **Immediate on payment** for every booking (Dispatch v2, §21.6.C). Frozen `booking_class` (instant/advance) drives policy; deferred `slot − 4h` advance start is rollback only |
| **Partner UX** | **Dual (§21.6.E):** instant (≤ `instant_lead_hours` away) → Rapido-style modal + Offers tab; advance → Offers **inbox**. An advance booking nearing its slot escalates to the modal (live `urgency`) |
| **Night slots** | **Blocked at launch (2a, §21.6.A):** 00:00–05:59 IST → 422 at `POST /v1/bookings` (`night_bookings_enabled=false`). Instant-night is permanently blocked. Night muhurats arrive in Phase 2 (§22 consultation) |
| **Reconfirmation** | **Mandatory** for advance bookings (≥24h lead); ping + escalation **shifted out of quiet hours** 22:00–08:00 (§21.6.H); partner **Yes** via `POST /v1/pujari/bookings/{id}/reconfirm`, **No** via `pujari-cancel` |
| **Panchangam** | **Server-cached** `GET /v1/panchangam` for customer **home ribbon** at launch (§23.6); calendar tab Phase 2 (`C-PANCHANGAM-CALENDAR`); vendor keys server-side only; Drik/Vakya labeled; home-ribbon fields (`vaaram`, `tithi`, `nakshatram`, `rahu_kalam`, `yama_gandam`, `sunrise`, `sunset`); accuracy gate before launch |
| **Contact** | **RM mediator** — both sides see RM name/phone; **no** customer↔pujari direct phone |
| **TDS (income-tax s.393)** | **OFF at launch** (`TDS_ACCRUAL_ENABLED=false`) — nothing accrued/withheld/deposited. Owner-accepted s.201 exposure uses **v3 model**: TDS on facilitation **after ₹5L FY** at **0.1%** on the crossing slice (operative PAN); **5% fail-safe** only above ₹5L without operative PAN — **not** 5%×all offline GMV from ₹1. Status + staging gates: [`TDS_LAUNCH_STATUS.md`](./TDS_LAUNCH_STATUS.md), [`TDS_STAGING_ROLLOUT.md`](./TDS_STAGING_ROLLOUT.md). **Primary mitigation: PAN drive + Setu verify.** |
| **After confirm** | Customer: pujari name + RM. Pujari: full address + static map link + RM |
| **DB safety nets** | **Keep** `intended_pujari_id`, trigger 3, `ex_bookings_intended_no_overlap` |

## Phase 2+ (defer)

| Area | Defer |
|------|-------|
| Direct booking (“book this pujari”) | Ratings / supply maturity |
| Pujari GPS + km-radius dispatch | Density + live matching |
| Live map tracking (customer sees pujari moving) | WS location events |
| Call masking (Exotel/Knowlarity) | After RM volume justifies |
| Dispatch filter by area (not just display) | Per-zone supply |
| Night slots (00:00–05:59) + night muhurats | §22 muhurat consultation — consulting-priest direct offer + real opt-in supply |
| ~~Telugu calendar / panchangam UI~~ | **Moved to launch (§23)** — server-cached API; **home ribbon** at launch (`C-PANCHANGAM-UI`); full calendar tab deferred (`C-PANCHANGAM-CALENDAR`) |
| Festival waitlist / pre-assign | Ops scale (Diwali, etc.) |
| Polygon geofencing | Not planned — dropdown preferred |

## Festival surge (risk note)

Peak festival days may exceed citywide broadcast capacity. Launch mitigates via RM
ops and manual intervention. Automated waitlist is **Phase 2+**.

## Implementation checklist (code — not done by spec-only pass)

See `plans/STATUS.md` §Puja MVP launch (P-LAUNCH-*). **Production go/no-go (OCI/Linux, migrations, TDS OFF):** [`MVP_GO_NO_GO_CHECKLIST.md`](./MVP_GO_NO_GO_CHECKLIST.md).
