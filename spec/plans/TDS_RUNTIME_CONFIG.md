# TDS runtime configuration — production vs staging (same code, different knobs)

**Purpose:** Single reference for ops and engineers. **Application code is identical** across
environments; behavior changes via **`.env`** (deploy flags + Setu URLs) and **`platform_settings` /
`tax_statutory_config`** (rates/thresholds without redeploy).

**Normative API:** [`API_CONTRACTS.md`](../API_CONTRACTS.md) · **FY gates:** [`PAN_FY_GATES.md`](./PAN_FY_GATES.md) ·
**Launch narrative:** [`TDS_LAUNCH_STATUS.md`](./TDS_LAUNCH_STATUS.md)

**Not in this doc:** Phase 3 deduction/deposit (`P-TDS-393`) — TAN, `pan_enc`, payout withhold.

**Production ops (checklists, month-end, sign-off):** [`TDS_PRODUCTION_OPS_READINESS.md`](./TDS_PRODUCTION_OPS_READINESS.md).

---

## Layer 1 — Environment (`.env` only)

Set on the API host. Restart **uvicorn** after changes. Never commit real secrets.

| Variable | Default | Effect |
|----------|---------|--------|
| `APP_ENV` | `development` | `production` enforces Setu PAN product id (503 if missing on PAN submit). |
| `DEBUG` | `false` | `true` → OTP may include `otp_dev_only` in auth responses (dev/staging only). |
| **Setu (swap sandbox ↔ prod URL + credentials)** | | |
| `KYC_SETU_BASE_URL` | `https://dg-sandbox.setu.co` | Production: `https://dg.setu.co` |
| `KYC_SETU_CLIENT_ID` / `KYC_SETU_CLIENT_SECRET` | empty | Setu bridge credentials (DigiLocker + PAN). |
| `KYC_SETU_DIGILOCKER_PRODUCT_ID` | empty | DigiLocker product instance. |
| **`KYC_SETU_PAN_PRODUCT_ID`** | empty | **PAN verify** product instance (`POST /api/verify/pan`). Required in prod for operative PAN. |
| `KYC_SETU_READ_TIMEOUT` | `25` | HTTP read timeout (seconds). |
| **TDS feature flags (boolean strings: `true` / `false`)** | | |
| `TDS_ACCRUAL_ENABLED` | `false` | When `true`, v3 accept-time FY + liability snapshot; balance ledger materialization; cancel reversal (T7). Does **not** deposit to government (Phase 3). |
| **`TDS_ACCEPT_STUB_COLLECT`** | `false` | Staging only: at accept, set **`tds_collected_online = liability`** (simulates customer TDS online). **Must be `false` for platform-bears** (full offline puja cash). |
| `PAN_ACCEPT_GATE_ENABLED` | `false` | Block **all** offer accept without PAN on file (`pan_hash`). |
| `PUJARI_TAX_PROFILE_REQUIRED_FOR_ACCEPT` | `false` | Block accept without PAN **and** `entity_type`. |
| `PUJARI_FY_PAN_GATE_ENABLED` | `false` | Block accept, heartbeat (go online), confirm-balance at **₹5L FY gross without PAN**; warn at ₹4.5L via API only. |

**Production checklist (minimal):**

1. `APP_ENV=production`, `DEBUG=false`
2. Setu **prod** base URL + secrets + **`KYC_SETU_PAN_PRODUCT_ID`**
3. Enable flags in order agreed with ops (often FY gate → accrual on staging first → prod)
4. Celery worker + beat running if `TDS_ACCRUAL_ENABLED=true`

---

## Layer 2 — Admin JSON (`platform_settings.tds_facilitation`)

**Commercial / UX thresholds** (not statutory filing rates). Tunable in **Admin → TDS & compliance**
without redeploy. Merged with code defaults in `load_tds_facilitation_config()`.

| JSON key | Default | Used for |
|----------|---------|----------|
| `individual_fy_pan_warn_inr` | `450000` | FY PAN **warn** tier (`fy_pan_gate_level=warn`) |
| `individual_fy_threshold_inr` | `500000` | FY PAN **block** tier + TDS accrual threshold (individual/HUF with PAN) |
| `no_pan_rate_pct` | `5` | Accrual when no PAN / inoperative (overridden by statutory table when present) |
| `pan_entity_rate_pct` | `0.1` | Accrual for always-taxed entities |
| `fy_turnover_warn_inr` / `fy_turnover_block_inr` | `1800000` / `2000000` | **Platform GST turnover** monitoring — not partner FY PAN gates |
| `always_taxed_entity_types` | firm, company, … | Entity types always subject to facilitation TDS logic |

Returned to clients on **`GET /v1/me/tax-summary`** (amounts as strings).

---

## Layer 3 — Statutory (`tax_statutory_config`, migration 027)

**R9:** Authoritative **TDS rate/threshold** fields for accrual when row exists. Admin/compliance
surface; do not edit casually. Accrual reads statutory first, then falls back to `platform_settings`
defaults (see `pricing.load_tds_facilitation_config`).

---

## Layer 4 — Public mobile mirror (`GET /v1/app-config`)

Read-only **booleans** copied from Layer 1 env (no secrets). Lets Flutter show the right entry points
(PAN step prominence, “TDS tracked” copy) **without hardcoding** staging vs prod.

| Field | Source env |
|-------|------------|
| `tds_accrual_enabled` | `TDS_ACCRUAL_ENABLED` |
| `pan_accept_gate_enabled` | `PAN_ACCEPT_GATE_ENABLED` |
| `pujari_tax_profile_required_for_accept` | `PUJARI_TAX_PROFILE_REQUIRED_FOR_ACCEPT` |
| `pujari_fy_pan_gate_enabled` | `PUJARI_FY_PAN_GATE_ENABLED` |
| `setu_pan_verify_configured` | non-empty `KYC_SETU_PAN_PRODUCT_ID` |

**Authoritative enforcement** remains on the API (422 on accept/heartbeat/confirm-balance). Mobile uses
**`GET /v1/me/tax-summary`** for warn/block **messages and amounts** (`fy_pan_gate_level`,
`individual_fy_pan_warn_inr`, `requires_pan_before_continue`).

---

## Code map (backend)

See [`TDS_CODE_REVIEW.md`](./plans/TDS_CODE_REVIEW.md) for module paths and review falsifiers.

| Concern | Module |
|---------|--------|
| Setu PAN | `setu_digilocker_client.verify_pan`, `pujari_compliance.submit_partner_pan` |
| FY gates | `pujari_fy_pan_gate.py` (**block tier: `pan_status = 'operative'`**) + wiring in `offer_service`, `pujaris.py`, `service_lifecycle.py` |
| v3 accept / FY writer | `tds_v3_accept_service.py`, `tds_v3_fy_writer.py`, `pricing_tds_v3.py` |
| Reversal (T7) | `tds_v3_reversal_service.py` |
| Accrual worker | `tds_accrual_service.py`, `app.workers.tds_accrual` (flag-gated) |
| Ledger net SQL | `tds_ledger_net_sql.py` (`LEDGER_TDS_NET_EXPR`, `LEDGER_GROSS_NET_EXPR`) |
| Readiness | `scripts/check_tds_readiness.py` |
| **CA 26Q export (read-only)** | **`scripts/export_tds_26q.py`** |
| Config load | `pricing.load_tds_facilitation_config`, `app/services/app_config.py` |
| Partner read APIs | `pujaris.py` tax-profile / tax-summary |

---

## What does **not** change per environment in code

- Endpoint paths and JSON shapes (`spec/openapi.json`)
- FY gross formula (sum `bookings.total_amount` with `balance_collected_at` in Indian FY)
- Setu success → `pan_status=operative`; failure → 422 in prod
- Phase 3 withhold/deposit (not implemented — separate milestone)
