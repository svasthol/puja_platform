# Mobile Flutter — implementation contract

**Purpose:** Normative mobile contract for `mana_guruji_mobile`. **Link and distill** backend
`spec/*` — do not redefine API behavior here.

**Repo:** `mana_guruji/mana_guruji_mobile` (sibling of `puja_platform`).

**Related:** [`MOBILE_FIREBASE.md`](./MOBILE_FIREBASE.md) · [`API_CONTRACTS.md`](./API_CONTRACTS.md) v3.4 ·
[`plans/FLUTTER_TDS_ALIGNMENT_PLAN.md`](./plans/FLUTTER_TDS_ALIGNMENT_PLAN.md) ·
[`plans/TDS_RUNTIME_CONFIG.md`](./plans/TDS_RUNTIME_CONFIG.md) ·
[`STACK_VERSIONS.md`](./STACK_VERSIONS.md) · [`plans/LAUNCH_POLICY.md`](./plans/LAUNCH_POLICY.md) ·
[`plans/PARTNER.md`](./plans/PARTNER.md) · [`plans/CUSTOMER.md`](./plans/CUSTOMER.md) ·
[`plans/STATUS.md`](./plans/STATUS.md) · [`openapi.json`](./openapi.json)

**Workspace:** Open Cursor at **`mana_guruji/`** (parent of both repos). Spec paths:
`puja_platform/spec/...`.

---

## Read these first (same order as backend `project.mdc`)

1. `spec/ARCHITECTURE.md`
2. `spec/DATABASE.md`
3. `spec/DISPATCH_FLOW.md`
4. `spec/API_CONTRACTS.md`
5. `spec/STACK_VERSIONS.md`
6. `spec/plans/MASTER.md`
7. `spec/plans/LAUNCH_POLICY.md`
8. `spec/plans/STATUS.md` — **the ONLY place task status lives**
9. `spec/plans/SPEC_AMENDMENTS.md`
10. `spec/MOBILE_FIREBASE.md`
11. **`spec/MOBILE_FLUTTER.md`** (this file)
12. Design handoff: `mana_guruji_mobile/docs/design/managuruji_design.html`

---

## Repo layout

| Path | Purpose |
|------|---------|
| `lib/main_customer.dart` / `lib/main_partner.dart` | Flavor entrypoints |
| `lib/features/customer/` | Customer app |
| `lib/features/partner/` | Partner (pujari) app |
| `lib/core/` | Theme, auth, network, FCM |
| `lib/api/generated/` | OpenAPI-generated Dio client — **never edit by hand** |
| `tool/generate_api.py` | Codegen from `openapi/openapi.json` |
| `openapi/openapi.json` | Copy of `puja_platform/spec/openapi.json` |

| Flavor | `applicationId` | OTP `app_context` |
|--------|-----------------|-------------------|
| customer | `com.managuruji.customer` | `customer` |
| partner | `com.managuruji.partner` | `pujari` |

---

## Contract status (LIVE vs PLANNED)

**Authority:** [`plans/STATUS.md`](./plans/STATUS.md) wins on conflict. This table is a
**convenience snapshot**. Before binding any endpoint, grep STATUS.md for the task ID and
confirm `COMPLETED`. "Spec done" requires a grep-confirmed line in the referenced spec file,
not a plan reference.

| Endpoint / field | STATUS task | State | Mobile may bind? |
|------------------|-------------|-------|------------------|
| `GET /v1/app-config` | `P-APP-CONFIG` | LIVE | Yes |
| `GET /v1/me/tax-summary` | `L-SPRINT-2-TDS-PARTNER-TAX-UI` | LIVE | Yes (partner) |
| `POST /v1/pujari/kyc/pan` | `L-SPRINT-2-TDS-KYC-PAN` | LIVE | Yes (partner) |
| `GET/PUT /v1/me/tax-profile` | `L-SPRINT-2-TDS-PAN-PROFILE` | LIVE | Yes (partner) |
| `GET /v1/panchangam` | `P-PANCHANGAM-API` | LIVE (contract) | Yes¹ (ribbon UI **IN_PROGRESS** — `C-PANCHANGAM-UI`) |
| `booking_class` (C-GET/list/create) | `P-FLUTTER-CONTRACT` | LIVE | Yes |
| `POST /v1/pujari/bookings/{id}/reconfirm` | `P-RECONFIRM-API` | LIVE | Yes |
| `spec/openapi.json` codegen | `P-OPENAPI-ARTIFACT` | LIVE | Yes |
| Partner KYC / register UI | `B-REGISTER`, `B-KYC` | COMPLETED (backend E2E) | **Yes** — implement `P-FLUTTER-REGISTER` + `P-FLUTTER-KYC` |
| Phase 3 tax / splits / payout UI | Phase 3 tasks | PLANNED | **No** |

¹ **Panchangam:** API + vendor cache COMPLETED. Customer ribbon implemented in Flutter;
`C-PANCHANGAM-UI` / `C-FLUTTER-PANCHANGAM` = **IN_PROGRESS** — device QA vs design 01
before COMPLETED in `STATUS.md`.
Regenerate client after `openapi.json` changes: `mana_guruji_mobile/tool/sync_openapi.ps1`.

---

## Launch policy (mobile)

From [`LAUNCH_POLICY.md`](./plans/LAUNCH_POLICY.md):

- **Broadcast only** — no direct pujari selection at checkout.
- **No pujari GPS at launch** — heartbeat lat/lng optional; dispatch is citywide.
- **RM, not direct phone** — after confirm, show RM contact; never customer phone on partner offers.
- **Area label only** on offer cards — `service_area_id` on address at checkout.
- **Night / instant rules** — from `GET /v1/app-config`; never hardcode.

---

## Dispatch v2 UX

From [`API_CONTRACTS.md`](./API_CONTRACTS.md) + [`PARTNER.md`](./plans/PARTNER.md) (`DV2-PARTNER-UX`):

| Signal | UX |
|--------|-----|
| `urgency` / `urgency_escalated` on offer | **Modal** (instant offer sheet) |
| `offer_advance` FCM | Inbox row on **Offers** tab |
| `offer_instant` FCM | Modal + Offers tab |
| Frozen `booking_class` on booking | Tracking / reconfirm branches — **not** the same as live `urgency` |
| Partner tabs | **Offers** (pending) vs **Bookings** (confirmed) — task `P-FLUTTER-PARTNER` |

**Partner accept errors** (no retry loops):

| HTTP | Meaning | UX |
|------|---------|-----|
| 409 | Already taken | "Just taken" |
| 410 | Expired / unavailable / customer cancelled | "Expired" or offer-unavailable string; **refresh inbox** (`refreshFromPush`) |

**Customer cancel → partner inbox:** Poll (20s) + 410 refresh are shipped. Real-time removal
via FCM `offer_withdrawn` (`P-FCM-CUSTOMER-CANCEL` — **COMPLETED** 2026-08-12).

### Customer cancel (`C-FLUTTER-CANCEL` — COMPLETED 2026-08-09)

Detail screen → status-aware dialog → `POST /v1/bookings/{id}/cancel` → refund snackbar →
pop + refresh booking list. Eligibility: `customer_cancel_eligibility.dart`.

### Partner cancel (`P-FLUTTER-PUJARI-CANCEL` — COMPLETED 2026-08-09)

Confirmed detail + reconfirm decline → `POST /v1/bookings/{id}/pujari-cancel` → navigate to
**Requests** tab + refresh offers (`partner_shell_intent.dart`).

---

## Auth

- `app_context` in OTP verify **body** (`customer` | `pujari`) — must match flavor.
- Tokens in `flutter_secure_storage`; refresh via Dio interceptor.
- On sign-out: reset Riverpod session state (duty, offers, bookings).

---

## Public config & panchangam

- **`GET /v1/app-config`** — `night_bookings_enabled`, `instant_lead_hours`, etc. (`P-APP-CONFIG`).
- **`GET /v1/panchangam`** only — no vendor API from app (`P-PANCHANGAM-API`).
  Home-ribbon fields (§23.6, migration 018): `date`, `vaaram`, `tithi`, `nakshatram`,
  `rahu_kalam`, `yama_gandam`, `sunrise`, `sunset`. Bind generated models to
  `PanchangamResponse` in `spec/openapi.json` — do not hardcode vendor shapes.

### Customer panchangam ribbon — **IN_PROGRESS**

**Status:** `C-PANCHANGAM-UI` / `C-FLUTTER-PANCHANGAM` = **IN_PROGRESS** in `STATUS.md`.

Scaffold: `lib/features/customer/customer_home_screen.dart`,
`lib/features/customer/widgets/panchangam_ribbon.dart`. Device-QA vs
`docs/design/managuruji_design.html` screen 01 before COMPLETED.

### Customer catalogue — **COMPLETED**

**Status:** `C-FLUTTER-CATALOG` = **COMPLETED** (device 2026-08-05). Sync matrix:
`spec/plans/CATALOG_SYNC.md`.

Screens: home categories + popular list (`customer_home_screen.dart`), full catalogue
(`customer_catalog_screen.dart` → design 02), puja detail (`customer_puja_detail_screen.dart`
→ design 03). APIs: `GET /v1/pujas` (with `category_id`), `GET /v1/pujas/{id}`. Detail CTA →
slot picker + checkout (`C-FLUTTER-CHECKOUT` **COMPLETED** 2026-08-06).

---

## WebSocket

- `web_socket_channel` + ticket from `POST /v1/ws-tickets`.
- **Not** Socket.IO.

---

## OpenAPI workflow

```powershell
cd mana_guruji_mobile
.\tool\sync_openapi.ps1          # copy + check + regenerate (Windows wrapper)
python tool/check_openapi_sync.py   # verify-only (CI / any OS)
python tool/generate_api.py
```

Extend `PHASE_A_PATHS` in `generate_api.py` per phase when adding endpoints.

---

## Stack versions

Authoritative: `pubspec.lock`, `.fvm/fvm_config.json`, `pyproject.toml`.
Human snapshot: [`STACK_VERSIONS.md`](./STACK_VERSIONS.md) (`<!-- stack-check -->` block).

After `flutter pub get` or FVM change:

```bash
python mana_guruji_mobile/tool/check_stack_versions_sync.py
```

---

## Implementation phases

| Phase | Scope | Status |
|-------|-------|--------|
| **A** | Flavors, OTP, FCM, partner heartbeat/offers/bookings list | Done |
| **B** | Design system, partner shell, customer catalogue + checkout + bookings | **IN_PROGRESS** |
| **B shipped** | Catalogue, address, checkout E2E, booking list/detail, **customer + partner cancel UX** | Done (2026-08-09) |
| **B shipped (TDS UX)** | Payment breakdown; partner FY tax summary + PAN profile; **FY PAN gates** (₹4.5L ⚠ / ₹5L block) — `PAN_FY_GATES.md` | Done (2026-09-14) |
| **B next (TDS QA)** | **Phase 0b + Flutter alignment COMPLETED** (2026-09-29): openapi sync, `FY_PAN_GATE_*` l10n by code, confirm-balance warn; staging device QA per `FLUTTER_TDS_ALIGNMENT_PLAN.md` Phase 1 | **COMPLETED** (code); device QA on staging |
| **B shipped** | Partner register + KYC onboarding UI (`P-FLUTTER-REGISTER`, `P-FLUTTER-KYC`) — device QA pending |
| **Blocked** | Razorpay tax UI (Phase 3), earnings strip | HOLD |

Track mobile tasks only in [`STATUS.md`](./plans/STATUS.md) (`C-FLUTTER-*`, `P-FLUTTER-*`).

---

## Design

- Handoff: `mana_guruji_mobile/docs/design/managuruji_design.html`
- Tokens: `mana_guruji_mobile/lib/core/theme.dart`
- Saffron reserved for instant / muhurat CTAs; peacock palette elsewhere.
- Production UI: no emoji in shipped widgets (design HTML may use placeholders).

---

## Do not build yet

- Earnings / payout money UI (Phase 3)
- Phase 3 tax snapshot / Razorpay Route settlement UI (basic checkout is **shipped** — `C-FLUTTER-CHECKOUT`)
- **Shipped (2026-09):** checkout/detail **payment breakdown** (puja vs platform fee vs total); partner **tax summary** + **PAN profile** screens — see `lib/core/booking_payment_breakdown.dart`, `partner_tax_summary_screen.dart`, `partner_pan_profile_screen.dart`
- `google_maps_flutter` until booking-detail maps slice (see STACK_VERSIONS PLANNED)
