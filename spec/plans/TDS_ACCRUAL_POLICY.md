# TDS accrual policy — CA-signed model (Sprint 2 / s.393 ex-194-O)

**Status:** NORMATIVE (owner + CA confirmed Sep 2026). **Superseded by [`TDS_V3_IMPLEMENTATION.md`](./TDS_V3_IMPLEMENTATION.md) where they differ.**
**Implementation:** `app/services/pricing.py` → `tds_on_facilitation()` (must match this doc before S14 flip).
**Companion:** [`PAN_FY_GATES.md`](./PAN_FY_GATES.md) (product warn/block), [`TDS_RUNTIME_CONFIG.md`](./TDS_RUNTIME_CONFIG.md) (flags/slabs),
[`TDS_LAUNCH_STATUS.md`](./TDS_LAUNCH_STATUS.md) (exit gates), [`KYC_ONBOARDING.md`](./KYC_ONBOARDING.md) (Aadhaar vs PAN).

**Store signed CA ref in:** `tax_statutory_config.advisor_signoff_ref` when statutory row is updated.

---

## 1. Who this applies to

| Actor | Role |
|-------|------|
| **Mana Guruji (platform)** | ECO / facilitator; sole proprietorship of operator does **not** change per-pujari rules below. |
| **Pujari (partner/priest)** | Tax subject for **facilitation gross** on collected puja value (`total_amount` at accrual — see R7 / §16). |
| **Default priest profile** | `entity_type = individual` (or `huf` — same threshold branch unless CA says otherwise). |

---

## 2. Partner onboarding vs tax profile (two tracks)

| Track | Required for dispatch? | Mechanism |
|-------|------------------------|-----------|
| **Aadhaar KYC** | **Yes** — must reach `pujari.verification_status = verified` | Setu **DigiLocker** → identity + address docs → **admin A-KYC approval** + profile photo (`KYC_ONBOARDING.md`). **Not** auto-verified on vendor fetch alone. |
| **PAN + entity type** | **No** at onboarding (flags default off) | Setu **PAN verify** (`KYC_SETU_PAN_PRODUCT_ID`, `POST /v1/pujari/kyc/pan`) → `pan_hash` + `pan_status=operative` in prod. Optional until FY gates bite. |

**Bookings:** Dispatch/eligibility requires **`verified`** (Aadhaar path complete), not PAN.

---

## 3. Product gates (FY facilitation gross — not TDS math)

FY gross = sum of `bookings.total_amount` with `balance_collected_at` in current Indian FY (see `PAN_FY_GATES.md`).

| FY gross | PAN on file + verified? | Product behavior (when `PUJARI_FY_PAN_GATE_ENABLED=true`) |
|----------|-------------------------|-----------------------------------------------------------|
| **< ₹4.5L** | Any | **OK** — no gate message required (tax-summary may still educate). |
| **₹4.5L – ₹5L** | No | **Warn** — upload PAN via Setu before ₹5L block; TDS still **₹0** in accrual. |
| **₹4.5L – ₹5L** | Yes (operative) | **Warn** — approaching ₹5L; TDS will apply after threshold. |
| **≥ ₹5L** | No | **Block** accept / go online / record balance + accrual uses **5%** (§4). |
| Crossing booking | No | **Accept-block (PAN Shield)** — accept is refused only when **this** booking's `total_amount` would push `fy_after` **> ₹5L** (projected), so no puja is delivered that later can't be recorded. Below-crossing bookings stay allowed (max supply). No 5% ever accrues while flag on. |
| **≥ ₹5L** | Yes (operative) | **No block** + accrual uses **0.1%** (§4). |

Warn at ₹4.5L is **UX only** — not a legal “PAN mandatory” moment unless block tier applies at ₹5L.

---

## 4. Accrual decision tree (individual / HUF) — CA model v2

**Input per collection:** `entity_type`, `fy_gross_before`, `this_amount`, `pan_on_file`, `pan_status` (operative per Setu in prod).

```
IF entity_type IN (individual, huf):
  IF fy_gross_before + this_amount <= individual_fy_threshold_inr (default ₹5,00,000):
    → TDS rate 0%, amount ₹0
  ELSE:  # strictly above ₹5L line on this booking's running FY math
    IF pan_on_file AND pan_status == operative:
      → TDS rate 0.1% (pan_entity_rate) on this_amount *
    ELSE:
      → TDS rate 5% (no_pan_rate) on this_amount *
ELSE IF entity_type IN always_taxed_entity_types (firm, company, trust, aop, other):
  → CA confirm: default remain 0.1% from ₹1 with operative PAN (peer ECO); document in memo if unchanged
ELSE:
  → park / 422 — entity_type required
```

\* **Crossing booking base:** CA to confirm whether TDS applies to **full** `this_amount` once FY crosses ₹5L, or only the slice above ₹5L. **Code today:** full `this_amount` when `fy_after > threshold`. Record answer in `TDS_CA_DECISION_MEMO.md` Q-crossing.

**Supersedes v13 fail-safe:** ~~no PAN → 5% from rupee one~~ for individual/HUF **below ₹5L**.

---

## 5. Rates (defaults — statutory table overrides)

| Knob | Default | When used (individual/HUF) |
|------|---------|----------------------------|
| `individual_fy_threshold_inr` | ₹5,00,000 | Zero-TDS band upper bound |
| `individual_fy_pan_warn_inr` | ₹4,50,000 | Product warn only |
| `pan_entity_rate_pct` | 0.1% | FY **>** threshold + operative PAN |
| `no_pan_rate_pct` | 5% | FY **>** threshold + no PAN or non-operative PAN |

Load statutory row **as-of** `collected_at` (R15) on accrual path.

---

## 6. §0.C exposure under v2 (OFF launch window)

While `TDS_ACCRUAL_ENABLED=false`, **no ledger** — exposure is **s.201 risk if accrual should have run**.

| Population | Principal model (v2) |
|------------|------------------------|
| Individual/HUF **under ₹5L** FY gross | **~₹0** TDS per collection (PAN or not) |
| Individual/HUF **over ₹5L**, PAN verified | **~0.1%** on taxable collections |
| Individual/HUF **over ₹5L**, no/unverified PAN | **~5%** on taxable collections + **block** when FY gate on |
| Always-taxed entities | **~0.1%** from ₹1 (unchanged until CA says otherwise) |

**Not** ~5% × entire offline GMV from day one for no-PAN priests (v13 plan error for this CA).

Owner signs §0.C with **`G`** = projected monthly offline GMV and **`s`** = share of GMV that **crosses ₹5L** without verified PAN (much smaller than 0.95 × all GMV).

---

## 7. Engineering checklist (Pass 2 — before S14)

| Step | Artifact |
|------|----------|
| 1 | This doc + amend `TDS_LAUNCH_STATUS.md` §0.C, `PAN_FY_GATES.md`, `TDS_RUNTIME_CONFIG.md` |
| 2 | Paste CA confirmation into `TDS_CA_DECISION_MEMO.md`; `advisor_signoff_ref` |
| 3 | `pricing.tds_on_facilitation` + tests (`test_tds_facilitation_settings`, `test_tds_accrual_decouple`, e2e #16) |
| 4 | Tax-summary / gate copy (no “5% from day one” for individuals) |
| 5 | `check_tds_readiness.py` — monitor **approaching/over ₹5L** and **post-5L no-PAN**, not nopan×5% on all GMV |
| 6 | `TDS_CODE_REVIEW.md` R10 row + reversion tests; dated review after merge |
| 7 | S14 staging: accrual ON, reconcile green, §11.1 backlog counts |

**Register:** Update **R10** remediation in `TDS_LAUNCH_STATUS.md` §7 to “5% only above ₹5L without operative PAN”; optional **R16** “v13 exposure doc drift” closed by Pass 2.

---

## 8. Out of scope (Phase 3 — §0.P3)

Withholding from payout, TAN deposit, 26Q / Form 16A, `pan_enc` filing, full `catch_up` retro — `P-TDS-393`.
