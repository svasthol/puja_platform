# Mana Guruji — Admin UI (Sprint 4A)

Next.js ops console for the puja platform. **Lives outside `app/`** — this is a separate frontend package, not imported by the FastAPI backend.

## Stack

See [COMPATIBILITY.md](./COMPATIBILITY.md) — aligned with `spec/STACK_VERSIONS.md` and `.cursor/rules/project.mdc`.

| Layer | Choice |
|---|---|
| Framework | Next.js 15 App Router |
| Data | TanStack Query v5 |
| Validation | Zod 3 |
| Styling | Tailwind CSS 3 |

## Prerequisites

- **Node.js 20 LTS or 22 LTS** (`>=20.18`, `<23`) — see `COMPATIBILITY.md`
- API running at `http://127.0.0.1:8000` with migration 009 applied
- `TOTP_ENC_KEYS` set; first admin bootstrapped (`scripts/bootstrap_admin.py`)
- Backend `ALLOWED_ORIGINS` includes `http://localhost:3000` and `http://127.0.0.1:3000` (default in `config.py`)

## Supported platforms

The admin UI runs on **Linux, Windows, and macOS** (any OS with Node 20/22). It talks to the API over HTTP only — no OS-specific code in `admin_ui/`.

| Task | Linux / macOS | Windows (PowerShell) |
|---|---|---|
| Copy env file | `cp .env.example .env.local` | `copy .env.example .env.local` |
| Install deps | `npm install` | same |
| Dev server | `npm run dev` | same |
| Production build | `npm run build` | same |
| Typecheck | `npm run typecheck` | same |

**API server (repo root, venv active):**

| | Linux / macOS | Windows |
|---|---|---|
| Normal start | `uvicorn app.main:app --reload --port 8000` | If DB calls fail, use selector loop below |
| psycopg async fix | not needed | `python -c "import asyncio; asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy()); import uvicorn; uvicorn.run('app.main:app', host='127.0.0.1', port=8000, reload=True)"` |

Open the UI at **http://localhost:3000** or **http://127.0.0.1:3000** (both are allowed in default CORS). Use either URL consistently in the browser.

Full backend setup (Postgres, Redis, Celery): `../CURSOR_SETUP.md` → [Supported platforms](../CURSOR_SETUP.md#supported-platforms).

## Quick start

From repo root:

**Linux / macOS**

```bash
cd admin_ui
cp .env.example .env.local
npm install
npm run dev
```

**Windows**

```powershell
cd admin_ui
copy .env.example .env.local
npm install
npm run dev
```

Open **http://localhost:3000** → redirects to `/console` (login if no session).

## What works

### Sprint 4A — shell

| Screen | API |
|---|---|
| TOTP login | `POST /v1/admin/auth/login` |
| Session / RBAC nav | `GET /v1/admin/me` |
| Advance amount | `GET/PUT /v1/admin/settings/advance-booking-amount` |
| Team roles | `GET/POST/DELETE /v1/admin/users/{id}/roles` |
| TOTP provision | `POST /v1/admin/users/{id}/credential` |

### Sprint 4B — catalogue builder (Wave 3)

| Screen | API |
|---|---|
| **Catalogue** (`/console/catalog`) | Categories CRUD, puja list per category, category image upload |
| **Puja builder** (`/console/catalog/pujas/[id]`) | Details, content (6 kinds), addons, hero + gallery media |

Catalogue writes require `admin` role. Media uploads use API proxy `PUT /v1/admin/catalog/media/{id}/upload`.

### Sprint 4B — Partners & pricing

| Screen | API |
|---|---|
| **Partners** (`/console/partners`) | `GET /v1/admin/pujaris` — search directory |
| **Pricing** (`/console/partners/[id]`) | `GET/PUT /v1/admin/pujaris/{id}/pricing` — replace-all matrix |

Writes require `admin` role. Prices flow through `pricing_resolver` for dispatch and customer quotes.

### Sprint 4B — KYC review (A-KYC)

| Screen | API |
|---|---|
| **KYC queue** (`/console/partners/kyc`) | `GET /v1/admin/kyc/pending` — pending current documents |
| Approve / reject | `POST /v1/admin/kyc/{doc_id}/approve` or `/reject` |

Approve/reject requires `admin` role. Support can view the queue. Pujari `verification_status` becomes `verified` only when identity, address, and photo are all approved. Document preview uses presigned URLs from `S3_BUCKET_KYC` when configured.

### Sprint 4C — booking operations

| Screen | API |
|---|---|
| **Bookings** (`/console/bookings`) | `GET /v1/admin/bookings` — search by phone, id, status, date |
| **Booking detail** (`/console/bookings/[id]`) | `GET /v1/admin/bookings/{id}` — 360° view; reassign, refund override, dispute, money read |
| **Failed refunds** (`/console/refunds`) | `GET /v1/admin/refunds?status=failed_permanent` |
| **Promos** (`/console/promos`) | `GET/POST/PUT /v1/admin/promos` |

Reassign and refund override are available to `support` (capped) and `admin` (uncapped). Promo writes require `admin` role.

## Auth

- Tokens in `sessionStorage` (tab-scoped)
- Auto-refresh on 401 via `POST /v1/auth/refresh`
- Admin access token TTL: 30 min (backend `ADMIN_ACCESS_TOKEN_EXPIRE_MINUTES`)

## Production CORS

Add your admin origin to the API `.env`:

```env
ALLOWED_ORIGINS=["http://localhost:3000","http://127.0.0.1:3000","https://admin.yourdomain.com"]
```

Restart the API after changing origins.

## Scripts

| Command | Purpose |
|---|---|
| `npm run dev` | Dev server on :3000 |
| `npm run build` | Production build |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run lint` | ESLint (Next.js) |
