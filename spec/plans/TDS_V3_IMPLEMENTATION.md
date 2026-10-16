# TDS v3 — implementation SSOT (launch: online collection Option A)

**Status:** NORMATIVE — supersedes [`TDS_ACCRUAL_POLICY.md`](./TDS_ACCRUAL_POLICY.md) wherever they differ.

## SUPERSEDES v2

| Topic | v2 | v3 |
|-------|----|----|
| Launch posture | Shadow accrual only | **TDS collected online** at checkout/accept (`booking_fee + TDS` on Razorpay) |
| Crossing base | Full `this_amount` on crossing booking | **`excess_slice`** — tax `min(amount, fy_after − ₹5L)` on crossing; full amount once latched |
| `gross_facilitation` | Same as ledger gross | **Turnover** = Σ full `total_amount`; ledger `gross_amount` = **taxable base** (slice) |
| Rounding | Per-accrual rupee (rejected) | **Deposit-level** s.288B — nearest **₹10** on challan total only; ledger stays paise |
| Latch | Phase 3 | **`deduction_latched`** on `pujari_tax_year` in Pass 2b |
| Reversal | One contra per booking | **Proportional** contra per `refund_reference`; never un-latch; return held TDS to customer |
| 5% path | Normal without PAN above ₹5L | **Fail-safe only** (inoperative PAN while latched); PAN gate blocks normal cross without PAN |

**Code:** `app/services/pricing_tds_v3.py` · **Migrations:** `migration_028.sql` … `migration_031.sql` (`tds_online_charge_closed_at`)

---

## Accrual math (individual / HUF)

1. If `fy_before + amount ≤ threshold` → rate 0, TDS 0, taxable 0.
2. Else choose rate: 5% if `use_no_pan_tds_rate`, else 0.1%.
3. Taxable base: if `deduction_latched` or `fy_before ≥ threshold` → full `amount`; else **excess_slice** `min(amount, fy_after − threshold)`.
4. TDS = `taxable × rate` (quantize paise `0.01`).
5. Set `deduction_latched = true` when `fy_after > threshold`.

Always-taxed entities: taxable = full amount from ₹1; latch N/A.

---

## T6 — Online TDS at accept (separate from ₹61 fee)

Pujari is unknown at booking creation — **never** attach TDS to the creation-time fee charge.

At **`accept_offer`** (after assignment accept UPDATE):

1. **PAN gate** with projected `total_amount` (before TDS compute).
2. `FOR UPDATE` booking + FY → `compute_facilitation_accrual` → `apply_fy_turnover_and_booking_snapshot`.
3. **Separate** Razorpay order for TDS only (`tds_razorpay_order_id`, idempotent receipt `tds-{booking_id}`).
4. **Success / stub:** `tds_collected_online = liability`, `amount_due_offline = total_amount − tds_collected_online` (never `− tds_liability_inr`; failed online → full offline + recovery).
5. **Charge failure:** booking still confirms; `tds_collected_online = 0`, `pujari_tds_recovery` pending row; close/clear `tds_razorpay_order_id`.

**Async checkout hazard:** pending TDS order must be **closed before offline collection** (`finalize_unresolved_tds_before_offline_collection` on confirm-balance). Webhook handler is idempotent — late pay after recovery/offline collection → **refund**, not shrink offline.

**Open CA — Q-recovery:** second customer checkout vs auth-capture vs periodic pujari settlement. Do not harden second-checkout UX until mechanism is signed off; staging uses `TDS_ACCEPT_STUB_COLLECT`.

Balance `_execute_accrual` **ledger-only** from snapshot (`tds_liability_inr` → ledger `tds_amount`).

Env: `TDS_ACCEPT_STUB_COLLECT=true` for staging/tests (instant collect without Razorpay).

---

## T7 — Reversal

`reverse_facilitation()` in `pricing_tds_v3.py` — proportional slice; **`apply_facilitation_reversal()`** in `tds_v3_reversal_service.py` implements FY decrement, ledger contra (`refund_reference` idempotent), online TDS refund vs recovery void, intent cancel, order close. **`sweep_never_collected_facilitation`** (Celery) full-reverses accepted-never-collected past grace.

`reverse_tds_on_cancel` delegates to T7 (legacy full cancel). Customer **`cancel_booking`** calls T7 with `refund_reference=cancel:{booking_id}`.

Cross-FY deposited TDS (Phase 3): carry credit / 26Q adjustment — no challan claw in service response note.

---

## Single-writer: FY turnover + latch

| Event | Pre-T6 (now) | At T6 |
|-------|----------------|-------|
| Compute taxable + rate | `_execute_accrual` if snapshot empty | **Booking confirmation** |
| `gross_facilitation += total_amount` | `apply_fy_turnover_and_booking_snapshot` | Same helper at confirmation |
| `deduction_latched` | Same helper (`OR` latch) | Same |
| Booking snapshot columns | Same helper | Same |
| Ledger insert | `_execute_accrual` always | `_execute_accrual` reads snapshot only |

If `bookings.tds_facilitation_fy_applied_at` is set, `_execute_accrual` **must not** increment FY — ledger materialization only.


1. Migrations 028+029  
2. `pricing.py` + `pricing_tds_v3.py` + unit tests  
3. T6 payment/offer wiring + staging tests  
4. T7 reversal + idempotency tests  
5. Accept projected gate + copy + `PAN_FY_GATES.md` — **done** (Sep 2026)  
6. Doc pack + v3 readiness script — **done** ([`TDS_READINESS.md`](./TDS_READINESS.md), `check_tds_readiness.py --strict`)  
7. Staging flags — **gated** ([`TDS_STAGING_ROLLOUT.md`](./TDS_STAGING_ROLLOUT.md); do not flip until migrate + clean FY + `--strict` green)  
8. **Close-out (Sep 2026)** — **done** (backend Sprint 2 scope; see § Close-out below)

---

## Close-out — platform-bears + CA export (Sep 2026)

**Posture:** Platform deposits statutory **0.1%** TDS from its own funds (booking-fee pool / treasury). Customer checkout stays **booking fee only** (~₹61); puja **`amount_due_offline = total_amount`**; **`tds_collected_online = 0`**. Accrual engine unchanged.

| Deliverable | Location | Notes |
|-------------|----------|--------|
| **26Q worksheet export** | `scripts/export_tds_26q.py` | Read-only CSV; `--month=YYYY-MM` or `--fy` + `--quarter`; **`LEDGER_TDS_NET_EXPR`** + **`LEDGER_GROSS_NET_EXPR`** from `tds_ledger_net_sql.py`; column **`amount_on_which_tds_deducted`** (ledger taxable-base net, not FY turnover); PAN + challan blank (CA fills PAN from KYC); footer **`deposit_round_inr`**. See `scripts/README.md`. |
| **Operative FY gate** | `pujari_fy_pan_gate.py` | ₹5L block/warn uses **`pan_status = 'operative'`**, not `pan_hash` alone — aligned with `use_no_pan_tds_rate`. |
| **Tests** | `tests/test_export_tds_26q.py`, `tests/test_pujari_fy_pan_gate_operative.py` | Export net + full reversal excluded; inoperative PAN blocked at accept when gate on. |

**Staging env (platform-bears):** `TDS_ACCRUAL_ENABLED=true`, `PUJARI_FY_PAN_GATE_ENABLED=true`, **`TDS_ACCEPT_STUB_COLLECT=false`**, `PAN_ACCEPT_GATE_ENABLED=false`. Do **not** use stub — it sets `tds_collected_online = liability` and shrinks offline cash.

**`pujari_tds_recovery` pending rows:** With stub off and no live Razorpay TDS order, accept/finalize may insert **`status='pending'`** recovery rows. In platform-bears that means **platform still owes this TDS**, not pujari collection. **Deposit amount for CA** comes from **ledger net** (export script), not recovery sum. `--strict` reconcile checks ledger vs `tds_accrued`, not recovery = 0.

**Dormant (unchanged):** `tds_v3_online_charge.py`, Razorpay TDS order, `TDS_ACCEPT_STUB_COLLECT=true` drills — left behind flags for optional future Q-recovery / customer TDS UX.

**Still Phase 3 (`P-TDS-393`):** TAN, in-app challan/deposit, automated 26Q/TRACES upload, **`pan_enc`** at KYC, payout withhold — not in this close-out.
