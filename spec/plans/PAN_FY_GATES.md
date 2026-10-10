# PAN FY gates — partner facilitation gross (Sprint 2 TDS UX + v3 accept)

**Status:** tracked in [`STATUS.md`](./STATUS.md) (`L-SPRINT-2-TDS-PAN-FY-GATES`).  
**Normative API:** [`API_CONTRACTS.md`](../API_CONTRACTS.md) § Partner tax summary / lifecycle errors.  
**Related:** [`TDS_LAUNCH_STATUS.md`](./TDS_LAUNCH_STATUS.md) §0.C, [`TDS_V3_IMPLEMENTATION.md`](./TDS_V3_IMPLEMENTATION.md), `PAN_ACCEPT_GATE_ENABLED` (global accept gate).

## Purpose (layman)

For **individual/HUF**, statutory TDS on facilitation applies only on the portion of FY turnover **above ₹5 lakh** — not on every rupee from day one. **0.1%** applies on that taxable slice when the partner has an **operative PAN** (Setu-verified). **5%** is a **fail-safe** when FY is already over ₹5L and PAN is missing or not operative — not the normal path below the threshold.

Product gates (unchanged intent):

1. **Warn at ₹4.5L** FY facilitation gross — nudge to add PAN / prepare for TDS (not the same as GST turnover warn at ₹18L).
2. **Block at ₹5L without operative PAN** — stop new work and new collections until PAN + entity type are complete (`PUJARI_FY_PAN_GATE_ENABLED`).

**Do not confuse** with admin `fy_turnover_warn_inr` / `fy_turnover_block_inr` (₹18L / ₹20L) — those monitor **platform fee revenue (GST)**, not pujari FY facilitation.

---

## TDS v3 at offer accept (`TDS_ACCRUAL_ENABLED=true`)

When accrual is on, accept is the **single writer** for FY turnover + latch + booking TDS snapshot (see `TDS_V3_IMPLEMENTATION.md`).

### Money split (partner-facing)

| Component | Meaning |
|-----------|---------|
| **Booking fee (online)** | Platform fee (~₹61) — separate Razorpay charge; not part of puja facilitation gross. |
| **TDS (online, when due)** | Separate Razorpay order for **`tds_liability_inr`** at accept when liability > 0 (stub or live per env). |
| **Offline due** | **`amount_due_offline = total_amount − tds_collected_online`** — full puja value minus TDS already collected online. **Not** `total − liability` when online collection failed (then offline stays full value + recovery row). |

Partners should see: pay/collect **booking fee + TDS online** where applicable; collect **remaining puja value offline** from the customer.

### Rates (after accept math)

| Situation | Rate on taxable slice |
|-----------|------------------------|
| Individual/HUF, FY **below** ₹5L | **0%** TDS liability |
| Individual/HUF, **crossing** ₹5L, operative PAN | **0.1%** on amount above threshold (this booking’s slice) |
| Individual/HUF, over ₹5L, **no / inoperative PAN** | **5%** fail-safe on taxable slice (avoid — use PAN gate + Setu verify) |
| Firm / company / trust / AOP / other | **0.1%** on full booking value (always-taxed entities) |

### Accept-time **projected** FY gate

When `PUJARI_FY_PAN_GATE_ENABLED=true`, block accept / go-online / record-balance if:

- Partner has **no PAN on file**, and  
- **FY facilitation gross** (balance-collected sum in current Indian FY) **or** **FY gross + this booking’s `total_amount`** reaches **₹5,00,000**.

This is evaluated **before** TDS liability is computed at accept — it prevents accepting a puja that cannot later be recorded without PAN once FY is latched.

**Distinct from** `PAN_ACCEPT_GATE_ENABLED` (blocks **all** accept without PAN regardless of FY).

### API hints on accept

`POST` accept-offer response includes (when v3 on): `tds_liability_inr`, `tds_collected_online_inr`, `amount_due_offline_inr`, `tds_recovery_pending`, `tds_razorpay_order_id`.

Tax summary (`GET /v1/me/tax-summary`) and `fy_pan_gate_message` carry warn/block copy aligned with this doc.

---

## FY gross basis

**`fy_gross_facilitation_inr`** for gates = sum of **`bookings.total_amount`** for the pujari where `balance_collected_at` falls in the current Indian FY (`fy_start` … `fy_end` exclusive). When TDS accrual is on, crossing bookings also increment **`pujari_tax_year.gross_facilitation`** at accept; gates use booking sum so behavior is correct while TDS is OFF.

## Thresholds (defaults)

| Knob | Default | Source |
|------|---------|--------|
| Warn | **₹4,50,000** | `individual_fy_pan_warn_inr` in `platform_settings.tds_facilitation` JSON |
| Block / statutory TDS threshold | **₹5,00,000** | `individual_fy_threshold_inr` (same as TDS accrual config) |

Admin TDS settings UI may expose warn later; code defaults apply if key absent.

## Who the warn/block applies to

| `pan_on_file` | `entity_type` | Warn (≥ ₹4.5L & < ₹5L) | Block (≥ ₹5L, no PAN) |
|---------------|---------------|-------------------------|------------------------|
| false | any | **Yes** — “Add PAN before ₹5L” | **Yes** |
| true | `individual` / `huf` | **Yes** — “Approaching ₹5L TDS (0.1% on slice above threshold)” | **No** (PAN present) |
| true | firm / company / trust / aop / other | No (always-taxed entity messaging via tax-summary) | **No** |

Block tier applies only when the partner does **not** have an **operative** PAN (`pan_status = 'operative'`) — an uploaded hash alone does not satisfy the ₹5L gate.

### Setu PAN verification (production)

| Env var | Purpose |
|---------|---------|
| `KYC_SETU_BASE_URL` | Sandbox `https://dg-sandbox.setu.co` / prod `https://dg.setu.co` |
| `KYC_SETU_CLIENT_ID` / `KYC_SETU_CLIENT_SECRET` | Same credentials as DigiLocker |
| **`KYC_SETU_PAN_PRODUCT_ID`** | PAN product instance id (not DigiLocker id) |

**Code path:** `SetuDigiLockerClient.verify_pan` → `pujari_compliance.submit_partner_pan` → `POST /v1/pujari/kyc/pan`. No S3 bucket for PAN verify (hash only). **Do not** mark `pan_status=operative` without successful Setu verify in production.

**Sandbox:** `ABCDE1234A` valid, `ABCDE1234B` invalid (Setu quickstart).

**Runtime config (env + admin slabs):** [`TDS_RUNTIME_CONFIG.md`](./TDS_RUNTIME_CONFIG.md).

---

## Enforcement (`PUJARI_FY_PAN_GATE_ENABLED`, default `false`)

When the env flag is **true**, block-tier actions return **422** with structured `detail`:

```json
{"code": "FY_PAN_GATE_BLOCKED", "message": "<English log copy>"}
```

Mobile localizes by **`code`** (same pattern as `INSTANT_NIGHT_BLOCKED`).

| Action | Endpoint | Rule |
|--------|----------|------|
| **Warn record balance (allow)** | `POST /v1/pujari/bookings/{id}/confirm-balance-collected` | At **warn** or **block** tier: **200** collected; `tds.message_code` = **`FY_PAN_GATE_WARN`** + `message` (Flutter localizes by code). **No FY 422** on this path — partner must not be stranded after performing the puja. |
| **Block accept offer** | accept path in offer service | No **operative PAN** and projected FY ≥ block threshold → **422** `FY_PAN_GATE_BLOCKED` |
| **Block go online** | `PUT /v1/me/heartbeat` | No **operative PAN** and `fy_gross` ≥ block threshold → **422** `FY_PAN_GATE_BLOCKED` |

**Not blocked:** `DELETE /v1/me/heartbeat` (go offline), completing in-progress bookings already accepted, admin paths.

**Not chosen:** blocking at warn tier only — warn is **UI + tax-summary** only.

### Interaction with global PAN gates

| Flag | Behavior |
|------|----------|
| `PAN_ACCEPT_GATE_ENABLED` | Blocks **all** accept without PAN (any FY gross) |
| `PUJARI_TAX_PROFILE_REQUIRED_FOR_ACCEPT` | Blocks accept without PAN **and** entity type |
| `PUJARI_FY_PAN_GATE_ENABLED` | Blocks accept / go-online at **₹5L+** without **operative PAN** (`pan_status = 'operative'`); confirm-balance **warn+allow** with `FY_PAN_GATE_WARN` |

Ops may enable FY gate first (late supply impact), then global accept gate after PAN drive. Staging order: [`TDS_STAGING_ROLLOUT.md`](./TDS_STAGING_ROLLOUT.md).

## API surface

### `GET /v1/me/tax-summary` (extended)

Additional fields:

- `individual_fy_pan_warn_inr` — `"450000.00"`
- `fy_pan_gate_level` — `ok` | `warn` | `block`
- `fy_pan_gate_message` — human copy for partner app
- `requires_pan_before_continue` — `true` when level is `block`

### Admin `GET /v1/admin/pujaris/fy-earnings`

Each row includes `fy_pan_gate_level` and `fy_gross_facilitation_inr` (TDS-aligned sum) for ⚠ sorting.

### Aadhaar / DigiLocker (admin)

KYC **does not re-download** from Setu on each view. Finalize flow stores identity/address proofs in **S3**; admin KYC queue **`view_url`** presigns those objects. Re-pull from DigiLocker is a separate feature request.

## Tests

- `tests/test_setu_pan_verify.py` — Setu PAN response parsing (mocked HTTP)
- `tests/test_pujari_fy_pan_gate.py` — warn/block math, 422 wiring when flag on
- `tests/test_pujari_fy_pan_gate_operative.py` — inoperative `pan_hash` blocked at ₹5L+ when gate on
- `tests/test_pujari_fy_pan_gate_confirm_balance.py` — block tier → **200** + `message_code=FY_PAN_GATE_WARN`, balance saved
- `tests/test_export_tds_26q.py` — ledger net export for CA worksheet
- Readiness: [`TDS_READINESS.md`](./TDS_READINESS.md) — over-₹5L without operative PAN; ledger net reconcile

## Flutter

- Tax summary + bookings entry: show **warning icon** when `fy_pan_gate_level == warn`
- Blocked actions: surface 422 message; link to PAN profile screen
- Accept success: show **offline due** from `amount_due_offline_inr`; explain **TDS** as separate online line when `tds_liability_inr` > 0
