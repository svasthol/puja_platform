# Getting started in Cursor — Step by step

Follow this exactly. Everything is already configured; you're just starting the engine.

---

## Supported platforms

The repo is **cross-platform**: develop on **Linux, Windows, or macOS**; deploy the API and workers on **Linux** (VM, Docker, K8s). Application code is OS-agnostic — only a few **local dev** commands differ.

| Task | Linux / macOS | Windows (PowerShell) |
|---|---|---|
| Install uv | `curl -LsSf https://astral.sh/uv/install.sh \| sh` | `irm https://astral.sh/uv/install.ps1 \| iex` |
| Activate venv | `source .venv/bin/activate` | `.\.venv\Scripts\Activate.ps1` |
| Copy env file | `cp ".env - Copy.example" .env` | `copy ".env - Copy.example" .env` |
| Run migrations | `alembic upgrade head` | same |
| Start API (normal) | `uvicorn app.main:app --reload --port 8000` | same *(if DB calls fail, use row below)* |
| Start API (psycopg async) | not needed — default loop is fine | see [Windows API note](#windows-api-note) below |
| Start Redis | `sudo systemctl start redis` or `brew services start redis` | Docker: `docker run -d -p 6379:6379 redis:7-alpine`, or WSL2 / Memurai |
| Celery worker | `celery -A app.workers.celery_app worker --loglevel=info -Q sweep,dispatch,refund,notifications` | add `--pool=solo` |
| Admin UI | `cd admin_ui && npm install && npm run dev` | same |

**Node.js (admin UI):** use **20 LTS** or **22 LTS** (`>=20.18`, `<23`). See `admin_ui/README.md`.

**Production:** Linux containers/VMs; no Windows-specific runtime paths in `app/` or `admin_ui/`.

### Windows API note

On Windows, `psycopg` async requires the **selector** event loop (not the default Proactor). Scripts and tests set this automatically when `sys.platform == "win32"`. For manual `uvicorn`:

```powershell
python -c "import asyncio; asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy()); import uvicorn; uvicorn.run('app.main:app', host='127.0.0.1', port=8000, reload=True)"
```

Linux and macOS do **not** need this.

---

## Prerequisites (install once on your laptop)

| Tool | Version | Install |
|---|---|---|
| Python | **3.12.x** | https://www.python.org/downloads/ |
| PostgreSQL | **16.x** | Already installed on your laptop ✅ |
| PostGIS | **3.x** | See below |
| Redis | **7.x** | https://redis.io/docs/install/ |
| uv | latest | `curl -Ls https://astral.sh/uv/install.sh \| sh` |

### Install PostGIS (required for dispatch radius queries)
- **macOS**: `brew install postgis`
- **Windows**: Open pgAdmin → Stack Builder → Spatial Extensions → PostGIS
- **Ubuntu/Debian**: `sudo apt install postgresql-16-postgis-3`

---

## Step 1: Open in Cursor

1. Open Cursor
2. File → Open Folder → select `puja_platform/`
3. Cursor auto-reads `.cursor/rules/project.mdc` — all AI rules are active

---

## Step 2: Create the Python virtual environment

Open the Cursor terminal (`Ctrl+`` ` ```) and run:

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create venv and install all pinned dependencies
uv venv --python 3.12
source .venv/bin/activate   # Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"

# After changing pyproject.toml dependencies, regenerate lock files:
#   uv pip compile pyproject.toml -o requirements.txt && uv pip compile pyproject.toml --extra dev -o requirements-dev.txt

# Verify versions match the matrix
python --version             # must be 3.12.x
python -c "import fastapi; print(fastapi.__version__)"   # 0.139.0
python -c "import sqlalchemy; print(sqlalchemy.__version__)"  # 2.0.44
python -c "import psycopg; print(psycopg.__version__)"   # 3.2.x
```

> **Windows users:** see [Supported platforms](#supported-platforms) for uv, Redis, Celery, and the API event-loop note.



---

## Step 3: Create the database

```bash
# In psql or pgAdmin, create the database
createdb Mana_Guruji

# Optional: create the app role (recommended for production-like local dev)
psql -c "CREATE ROLE puja_app WITH LOGIN PASSWORD 'dev_password';"
psql -c "GRANT CONNECT ON DATABASE Mana_Guruji TO puja_app;"
```

---

## Step 4: Configure environment

```bash
cp .env.example .env
# Edit .env — set DATABASE_URL with your local Postgres credentials
# Minimum required for local dev:
#   DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/Mana_Guruji
#   SECRET_KEY=any-32-char-string-for-local-dev-only
```

---

## Step 5: Run migrations (loads the validated schema + all triggers)

```bash
# Make sure you're in the project root with .venv active
alembic upgrade head

# Expected output:
#   INFO  [alembic.runtime.migration] Running upgrade  -> 001, Initial schema
#   INFO  [alembic.runtime.migration] Running upgrade 001 -> 002, Dispatch...
#   INFO  [alembic.runtime.migration] Running upgrade 002 -> 003, Dual payment...
#
# Zero errors expected.
# If you see "btree_gist does not exist" → install PostGIS/contrib (step 0)
```

---

## Step 6: Start the API

```bash
uvicorn app.main:app --reload --port 8000
# Visit http://localhost:8000/docs  (Swagger UI — dev only)
# Visit http://localhost:8000/health
```

On **Windows**, if DB endpoints error at runtime, use the [Windows API note](#windows-api-note) instead of plain `uvicorn`.

---

## Step 7: Start Redis (for Celery)

See [Supported platforms](#supported-platforms) for OS-specific Redis commands.

---

## Step 8: Start the Celery sweep worker

```bash
# In a separate terminal (venv active)
celery -A app.workers.celery_app worker --loglevel=info -Q sweep,dispatch,refund,notifications
celery -A app.workers.celery_app beat --loglevel=info   # scheduler (30s sweep)
# (app/workers/celery_app.py is the real module — verified to import cleanly)
```

> **Windows:** add `--pool=solo` — see [Supported platforms](#supported-platforms).

---

## Step 10: Full booking flow (E2E)

See `scripts/dev_booking_flow_e2e.py` for an automated walkthrough, or follow manually:

1. Customer OTP auth → `POST /v1/auth/otp/request` + `/verify`
2. `POST /v1/slot-holds` (omit `pujari_id` for broadcast)
3. `POST /v1/bookings` (creates Razorpay test order — needs `RAZORPAY_KEY_ID/SECRET`)
4. Mock payment: `POST /v1/webhooks/razorpay` with `X-Razorpay-Signature`
   (use `scripts/sign_razorpay_webhook.py` to generate body + signature locally)
5. Dispatch: Celery worker runs `broadcast_booking`, or call it from Python shell
6. Set Redis `presence:{pujari_id}` before dispatch (pujari must be "online")
7. Pujari OTP auth with `?app_context=pujari` → `GET /v1/offers` → `POST .../accept`

**Webhook secret:** `RAZORPAY_WEBHOOK_SECRET` is NOT the API key secret. For local
mock webhooks, set any string in `.env` and sign with the same value. In production,
use the signing secret from Razorpay Dashboard → Webhooks.

```bash
python scripts/dev_booking_flow_e2e.py
```

**Interactive manual walkthrough** (pauses after each step, prints DB rows):

```bash
python scripts/manual_verify_session.py
# Uses your phone +917675834207; OTP from uvicorn log when DEBUG=true
```

---

## Step 9: Quick API smoke (optional)

```bash
python scripts/dev_api_smoke.py
# Expect: health 200, otp flow 202/200, pujas 200, checkout/quote 200, smoke_ok
```

---

## How to use Cursor AI effectively

**Always start a chat with context:**
> "Read spec/ARCHITECTURE.md and spec/API_CONTRACTS.md, then implement the
> `POST /v1/auth/otp/request` endpoint in `app/api/v1/endpoints/auth.py`."

**Feature-by-feature order (recommended):**
1. `POST /v1/auth/otp/request` + `/verify` + `/refresh` + `/logout`
2. `GET /v1/pujas` catalog endpoint
3. `POST /v1/slot-holds`
4. `POST /v1/bookings` (the big one — validate hold FOR UPDATE, create Razorpay order)
5. `POST /v1/webhooks/razorpay`
6. `GET /v1/offers` + `POST .../accept` + `.../reject`
7. WS endpoints

**Cursor prompt template:**
```
Read spec/API_CONTRACTS.md carefully.
Implement [ENDPOINT] in app/api/v1/endpoints/[file].py.
Rules:
- Use AsyncSession from app.db.engine.get_db
- Map all DB errors via the exception handler in app/core/exceptions.py
- Do NOT write bookings.pujari_id directly (trigger 3 does it)
- All auth goes through app.core.dependencies.get_current_user
Return only the code, no explanation needed.
```

---

## Common mistakes Cursor might make (watch for these)

| Mistake | Correct |
|---|---|
| `from psycopg2 import ...` | `from psycopg import ...` |
| `from jose import jwt` | `from jwt import PyJWT` or `import jwt` |
| `session.query(Model)` | `select(Model)` with `await session.execute()` |
| `Column(String)` in model | `name: Mapped[str] = mapped_column(String)` |
| Calling Razorpay refund API in a request handler | Insert a `refunds` row; let the worker call it |
| Writing `bookings.pujari_id = pujari_id` | Never — trigger 3 does this |
| Reading `pujaris.is_online` for dispatch | `redis.get(f"presence:{pujari_id}")` |
