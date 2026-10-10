# Flutter ↔ backend TDS alignment plan (no contract drift)

**Authority:** Backend behavior = [`API_CONTRACTS.md`](../API_CONTRACTS.md) + [`openapi.json`](../openapi.json).
Mobile rules = [`MOBILE_FLUTTER.md`](../MOBILE_FLUTTER.md) + [`.cursor/rules/project.mdc`](../../.cursor/rules/project.mdc).
Task status = [`STATUS.md`](./STATUS.md) only.

**Scope:** Sprint 2 TDS **UX** (PAN verify, tax profile, FY summary, payment breakdown, gate banners).
**Out of scope:** Phase 3 earnings, Razorpay Route withhold, TAN/deposit UI (`P-FLUTTER-EARNINGS-UI` HOLD).

**Runtime knobs:** [`TDS_RUNTIME_CONFIG.md`](./TDS_RUNTIME_CONFIG.md) — same app binaries; API `.env` + admin slabs differ by environment.

---

## Principle: one contract, two clients

| Rule | Why |
|------|-----|
| **Never hardcode** ₹4.5L / ₹5L / TDS % in Flutter | Amounts come from `GET /v1/me/tax-summary` and admin-tuned backend config. |
| **Never infer gate enforcement** from local state alone | Server returns **422** `FY_PAN_GATE_BLOCKED` on accept / heartbeat; confirm-balance returns **200** with `tds.message_code=FY_PAN_GATE_WARN` when applicable. UI localizes by **code** (EN/TE). |
| **Regenerate Dio client** after every `openapi.json` change | `mana_guruji_mobile/tool/sync_openapi.ps1` → `lib/api/generated/`. |
| **Partner flavor only** for PAN/TDS screens | Customer app: checkout/detail **breakdown** only (no PAN). |
| **Copy for “TDS deducted”** | Use tax-summary + l10n “tracked (not deducted yet)” until Phase 3. |

---

## Backend endpoints ↔ Flutter surfaces

| Endpoint | Method | Flutter location | STATUS task |
|----------|--------|------------------|-------------|
| `GET /v1/app-config` | public | TDS flags via `partner_tds_flags_provider` | `P-FLUTTER-TDS-ALIGNMENT` ✓ |
| `POST /v1/pujari/kyc/pan` | partner | `partner_pan_profile_screen.dart`, KYC hub | `P-FLUTTER-PAN-PROFILE` ✓ |
| `GET /v1/me/tax-profile` | partner | Pre-fill entity type; completeness checks | `P-FLUTTER-PAN-PROFILE` ✓ |
| `PUT /v1/me/tax-profile` | partner | Entity type only (PAN via POST pan) | `P-FLUTTER-PAN-PROFILE` ✓ |
| `GET /v1/me/tax-summary` | partner | `partner_tax_summary_screen.dart`, bookings tab banner | `P-FLUTTER-TAX-SUMMARY` ✓ |
| Payment breakdown fields | customer/partner | `booking_payment_breakdown.dart` + checkout/detail | `P-FLUTTER-BILLING-BREAKDOWN` ✓ |
| `POST /v1/offers/{id}/accept` | partner | `offers_controller` — map **422** PAN/FY messages | `P-FLUTTER-PAN-FY-GATE-UX` ✓ |
| `PUT /v1/me/heartbeat` | partner | Go-online — map **422** FY PAN block | `P-FLUTTER-ONLINE` ✓ |
| Confirm balance collected | partner | Booking lifecycle — **no FY 422**; snackbar from `tds.message_code` **`FY_PAN_GATE_WARN`** | `P-FLUTTER-TDS-ALIGNMENT` ✓ |

**Field binding (tax-summary):**

| JSON field | Flutter use |
|------------|-------------|
| `fy_gross_facilitation` | FY gross row |
| `tds_accrued` | Accrued row (informational) |
| `threshold_remaining_inr` | Remaining to ₹5L threshold |
| `fy_pan_gate_level` | `ok` \| `warn` \| `block` — banner icon/color |
| `fy_pan_gate_message` | English log copy only — **do not** use as primary TE banner (use `fy_pan_gate_level` + l10n) |
| `TdsAccrualInfo.message_code` | On confirm-balance: **`FY_PAN_GATE_WARN`** → localize like 422 gate codes |
| `individual_fy_pan_warn_inr` | Optional subtitle / debug |
| `requires_pan_before_continue` | CTA to open PAN screen when true |
| `message` | General FY/TDS copy |

**PAN submit body (must match OpenAPI):**

```json
{
  "pan": "ABCDE1234A",
  "entity_type": "individual",
  "consent": true,
  "reason": "≥20 characters for Setu contract"
}
```

**PAN submit response:** show `verified_name` when present; surface `pan_status` on failure (`422` detail).

---

## Execution phases (Flutter repo)

### Phase 0 — Contract lock (before any UI change)

1. Copy `puja_platform/spec/openapi.json` → mobile (`sync_openapi.ps1`).
2. Extend `tool/generate_api.py` `PHASE_A_PATHS` if new paths missing from generated client.
3. Grep mobile for hardcoded `450000`, `500000`, `4.5`, `5 lakh` — remove or replace with API-driven strings.
4. Confirm `POST /v1/pujari/kyc/pan`, `GET /v1/me/tax-summary`, and `GET/PUT /v1/me/tax-profile` exist in generated `mana_guruji_api.dart` (`tool/generate_api.py` `PHASE_A_PATHS`).

**Exit:** `python tool/check_openapi_sync.py` green.

### Phase 0b — FY gate error codes (backend + OpenAPI) — **COMPLETED 2026-09-29**

| Code | When | Client |
|------|------|--------|
| `FY_PAN_GATE_BLOCKED` | 422 on accept + `PUT /me/heartbeat` | Modal + PAN CTA; l10n by code |
| `FY_PAN_GATE_WARN` | 200 confirm-balance when warn/block tier | `TdsAccrualInfo.message_code`; l10n by code (non-blocking snackbar) |

Confirm-balance **does not** FY-422 (partner can close in-progress work). Spec: [`PAN_FY_GATES.md`](./PAN_FY_GATES.md), [`API_CONTRACTS.md`](../API_CONTRACTS.md).

### Phase 1 — Shipped screens — device QA (no new features required)

Track: `P-FLUTTER-E2E-SMOKE` extension **TDS slice**.

| # | Flow | Pass criteria |
|---|------|----------------|
| 1 | Partner OTP `+910000000011` (seed) | Token saved |
| 2 | KYC hub → PAN screen → valid PAN + consent + reason | 200, snackbar; optional show `verified_name` |
| 3 | Invalid PAN (sandbox B) | 422, user-readable error |
| 4 | Bookings tab → Tax summary | Rows match API; warn banner if staging data ≥ ₹4.5L |
| 5 | Customer checkout + booking detail | Breakdown lines match API amounts |
| 6 | With `PUJARI_FY_PAN_GATE_ENABLED=true` on API | Accept / go-online → **localized** block dialog (`FY_PAN_GATE_BLOCKED`); confirm-balance → **200** + `FY_PAN_GATE_WARN` snackbar |

**Exit:** Checklist pasted in test doc or STATUS comment; partner build against **staging API** with prod-like flags.

### Phase 2 — Collision fixes (small, targeted)

| Gap | Fix |
|-----|-----|
| 422 on accept/heartbeat generic snackbar | Map `DioException` response `detail` string; if contains “PAN”, route to `PartnerPanProfileScreen` |
| `app-config` TDS flags | After codegen: optional banner “PAN required to accept offers” when `pan_accept_gate_enabled` |
| Reason field l10n | Move “Consent reason (min 20 chars)” to `app_en.arb` / `app_te.arb` |
| Success UX | Show `verified_name` from PAN response in snackbar or dialog |

**Exit:** PR in `mana_guruji_mobile` only; no backend change unless contract gap found.

### Phase 3 — Blocked (do not implement)

- Earnings header / payout splits
- “TDS deducted from your bank account”
- Form 16A / TRACES / deposit status
- Customer PAN or TDS screens

---

## Error matrix (partner)

| HTTP | Endpoint context | Flutter action |
|------|-------------------|----------------|
| 422 | PAN verify failed | Show `detail`; do not pop screen |
| 422 | FY PAN gate block | Show `detail`; CTA → PAN profile |
| 422 | Tax profile required for accept | CTA → PAN profile |
| 503 | PAN submit in prod without Setu product | “Verification temporarily unavailable” (ops) |
| 409 / 410 | Accept race | Existing offers UX (refresh inbox) |

Messages are **English from API** today; wrap with l10n only where product adds TE paraphrase — do not change meaning.

---

## Admin / E2E (not Flutter)

| Surface | Repo |
|---------|------|
| TDS slabs admin | `admin_ui` → `/console/settings/tds` |
| FY earnings report | `admin_ui` → `/console/partners/fy-earnings` |
| Manual Setu PAN test | `tests/e2e_ui` Partner tab v19+ |

---

## Sign-off checklist (engineering)

- [ ] `openapi.json` in sync; mobile codegen run
- [ ] Phase 1 device QA on staging API with Setu PAN product configured
- [ ] No hardcoded FY thresholds in Dart
- [ ] `STATUS.md`: `P-FLUTTER-PAN-PROFILE`, `P-FLUTTER-TAX-SUMMARY`, `P-FLUTTER-PAN-FY-GATE-UX`, `P-FLUTTER-BILLING-BREAKDOWN` remain **COMPLETED**; E2E smoke TDS slice **PASS**
- [ ] Ops: `.env` documented in [`TDS_RUNTIME_CONFIG.md`](./TDS_RUNTIME_CONFIG.md) for prod cutover

**Product sign-off** (human): CA memo, risk, PAN drive, S14 accrual on staging — see `TDS_LAUNCH_STATUS.md`.
