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
| Puja `is_active=true` | Shown | **Shown** | Name on offer/booking when dispatched |
| Puja `is_active=false` | Shown (Off badge) | **Hidden** | N/A (not in customer catalogue) |
| Category `is_active=true` | Shown | In `categories` array | N/A |
| Category `is_active=false` | Shown | **Hidden** from `categories` | N/A |
| Content / addons | Full CRUD | Detail only (`inclusion`, `exclusion`, …) | N/A |
| Media | Upload + assign hero | `hero_image_url` when `upload_status=ready` | N/A |

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

| Screen | Design ref | API | Status |
|--------|------------|-----|--------|
| Home categories row | design 01 | `categories` from `GET /v1/pujas` | IN_PROGRESS |
| Home popular list + See all | design 01 | same, `limit=8` | IN_PROGRESS |
| Full catalogue + chips | design 02 | `GET /v1/pujas?category_id=` + cursor | IN_PROGRESS |
| Puja detail | design 03 | `GET /v1/pujas/{id}` | IN_PROGRESS |
| Checkout / slot pick | design checkout | `slot-holds`, `bookings` | PENDING (Wave 4) |
| Addresses | Account → saved addresses | `GET/POST/PUT /v1/addresses`, `GET /v1/service-areas` | IN_PROGRESS (`C-FLUTTER-ADDR`) |

---

## Troubleshooting “Admin shows puja, customer doesn’t”

1. Puja badge **Active** (not Off) in Admin → Catalogue.
2. Category **enabled** (customer `categories` list is active-only).
3. Customer app signed in with **customer** flavor (`app_context=customer`).
4. Same API host: Admin `127.0.0.1:8000` ≡ emulator `10.0.2.2:8000`.
5. Pull to refresh on customer home or open full catalogue.

---

## Partner app

Partner does **not** implement catalogue browse. Sync is via **booking/offer payloads** (`puja_name`, `duration`, schedule) from dispatch APIs — aligned with backend `C-PUJAS` read model at booking time.
