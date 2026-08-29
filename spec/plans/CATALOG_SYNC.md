# Catalogue sync matrix (Admin ↔ Backend ↔ Customer ↔ Partner)

**Normative API surface:** `spec/API_CONTRACTS.md` · **Task status:** `spec/plans/STATUS.md` only.

Single Postgres catalogue. Clients differ by **endpoint**, **auth**, and **visibility rules** — not by separate databases.

---

## Data flow

```
Admin UI  ──write──►  /admin/catalog/*  ──►  pujas, puja_categories, content, addons, media
                              │
                              ▼
                         PostgreSQL (same rows)
                              │
         ┌────────────────────┼────────────────────┐
         ▼                    ▼                    ▼
 GET /v1/pujas          GET /admin/catalog/pujas   offers / bookings
 (customer JWT)          (admin JWT)                (puja_name on card)
 Customer app            Admin UI                   Partner app
```

---

## Visibility rules

| Entity | Admin `GET /admin/catalog/pujas` | Customer `GET /v1/pujas` | Partner app |
|--------|----------------------------------|--------------------------|-------------|
| Puja `is_active=true` | Shown | **Shown only if** at least one **verified** pujari has `pujari_pricing` for that puja | Name on offer/booking when dispatched |
| Puja `is_active=false` | Shown (Off badge) | **Hidden** | N/A (not in customer catalogue) |
| Category `is_active=true` | Shown | In `categories` array | N/A |
| Category `is_active=false` | Shown | **Hidden** from `categories` | N/A |
| Content / addons | Full CRUD | Detail only (`inclusion`, `exclusion`, …); addon `image_url` when media `ready` | N/A |
| Media | Upload + assign hero | `hero_image_url` when `upload_status=ready`; addon thumbnails via `image_url` | N/A |

**Create defaults (admin API):** new category and puja are created with `is_active=true`.

---

## Endpoint map

| Action | Admin UI | Customer Flutter | Backend |
|--------|----------|-------------------|---------|
| List categories + pujas | `GET /admin/catalog/categories`, `GET /admin/catalog/pujas` | `GET /v1/pujas` (`category_id` filter optional) | `catalog.py`, `admin_catalog.py` |
| Puja detail | `GET /admin/catalog/pujas/{id}` + content/addons | `GET /v1/pujas/{id}` | `catalog.py` |
| Create puja | `POST /admin/catalog/pujas` | — | `admin_catalog.py` |
| Customer auth | Admin TOTP | OTP `app_context=customer` | `auth.py` |
| Partner catalogue browse | — | — | **Not in scope** — `puja_name` on offers/bookings |

---

## Flutter customer catalogue (C-FLUTTER-CUSTOMER Wave 2)

**Status:** see `STATUS.md` — `C-FLUTTER-CATALOG`, `C-FLUTTER-ADDR`, `C-FLUTTER-CHECKOUT` =
**COMPLETED** (device-verified 2026-08-05 / 2026-08-06). This table is a screen map, not the
status tracker.

| Screen | Design ref | API | STATUS task |
|--------|------------|-----|-------------|
| Home categories row | design 01 | `categories` from `GET /v1/pujas` | `C-FLUTTER-CATALOG` |
| Home popular list + See all | design 01 | same, `limit=8` | `C-FLUTTER-CATALOG` |
| Full catalogue + chips | design 02 | `GET /v1/pujas?category_id=` + cursor | `C-FLUTTER-CATALOG` |
| Puja detail | design 03 | `GET /v1/pujas/{id}` | `C-FLUTTER-CATALOG` |
| Checkout / slot pick | design checkout | `slot-holds`, `bookings` | `C-FLUTTER-CHECKOUT` |
| Addresses | Account → saved addresses | `GET/POST/PUT /v1/addresses`, `GET /v1/service-areas` | `C-FLUTTER-ADDR` |

---

## Troubleshooting “Admin shows puja, customer doesn’t”

1. Puja badge **Active** (not Off) in Admin → Catalogue.
2. Category **enabled** (customer `categories` list is active-only).
3. At least one **verified** pujari has **`pujari_pricing`** for the puja (customer `GET /v1/pujas` filters on this; admin list does not).
4. Customer app signed in with **customer** flavor (`app_context=customer`).
5. Same API host: Admin `127.0.0.1:8000` ≡ device LAN IP (e.g. `192.168.1.5:8000`).
6. Pull to refresh on customer home or open full catalogue.
7. **Dev backfill:** after seeding catalogue or adding pujas, run  
   `python scripts/sync_active_puja_pricing.py`  
   (links every active puja to every verified pujari at `default_price`).
8. **Production path:** when admin KYC promotes a pujari to `verified`, the API auto-applies
   city service-area links, default weekly hours (06:00–23:59), and catalogue pricing via
   `partner_dispatch_readiness.ensure_partner_dispatch_readiness()`. New admin puja creates
   call `ensure_puja_pricing_for_verified_pujaris()`. Dev scripts remain for one-off DB repair.

---

## Partner app

Partner does **not** implement catalogue browse. Sync is via **booking/offer payloads** (`puja_name`, `duration`, schedule) from dispatch APIs — aligned with backend `C-PUJAS` read model at booking time.
