# E2E test UI (manual QA only)

**Not part of the product.** Static HTML + a tiny local proxy for exercising the real API
without touching `app/`. Do not deploy, bundle, or import from production code.

## What it covers

- Customer: OTP login → address → slot hold → booking → Razorpay test checkout
- Optional: mock `payment.captured` webhook (local dev, no ngrok)
- Partner: OTP login (`app_context=pujari`) → heartbeat → list/accept offers
- **Admin (Phase 4):** TOTP login (`POST /admin/auth/login`) → settings, roles, credential provisioning, **catalogue smoke (4B)**
- **Test ops:** read-only booking dashboard (`GET /test-bookings.json`) — validates DB rows during E2E

## Prerequisites

1. API running: `uvicorn app.main:app --reload --port 8000`
2. `DEBUG=true` in `.env` (OTP printed in uvicorn logs)
3. Celery worker on `dispatch` queue (for offers after payment)
4. **Seed DB once:** `python tests/e2e_ui/ensure_seed.py` — creates `pujaris` rows (OTP login alone does **not**)
5. Partner tab: use phone **`+910000000011`** after seed (personal numbers get 403 on heartbeat)
6. Razorpay **test** `RAZORPAY_KEY_ID` in the UI settings (public key only)

## Run the test UI

```powershell
cd C:\OM\Guruji\mana_guruji\puja_platform
.\.venv\Scripts\activate
python tests/e2e_ui/serve.py
```

**If Test ops shows 404 / HTML error:** two stale servers often cause this. Use the restart helper instead:

```powershell
powershell -ExecutionPolicy Bypass -File tests/e2e_ui/run_serve.ps1
```

Then verify: http://127.0.0.1:8765/e2e-ui-version.json → should show `"version": "7"`.

Open **http://127.0.0.1:8765**

### Test ops dashboard

Open the **Test ops** tab (or leave it open while testing on Customer tab with auto-refresh).

| Column | Validates |
|---|---|
| Status | `bookings` → `status_types` |
| Paid | `bookings.paid_at` set after webhook |
| Payment ID | `payments.gateway_txn_id` |
| Offers | `booking_assignments` count (dispatch ran?) |
| Pujari | assigned after accept → `confirmed` |

Data comes from read-only SQL in `test_db.py` via `GET /test-bookings.json` — **not** a production API.

Optional env:

```powershell
$env:E2E_API_UPSTREAM="http://127.0.0.1:8000"   # default
$env:E2E_UI_PORT="8765"                          # default
```

## OTP / SMS (Phase 2) — confirm integration (tests only)

Uses **server-driven OTP** (`POST /v1/auth/otp/request` + `/verify`). Providers: FAST2SMS (primary) → MSG91 (failover when enabled).

| Mode | `.env` | How to get OTP |
|---|---|---|
| **FAST2SMS direct** | `FAST2SMS_API_KEY` | OTP / SMS tab → **Send OTP via FAST2SMS (direct)** — no uvicorn needed |
| **FAST2SMS via API** | `FAST2SMS_API_KEY`, `SMS_PROVIDER_ORDER=fast2sms,msg91` | Request OTP → `sms_sent: true`, `sms_provider: fast2sms` |
| **Dev** | `DEBUG=true` | Uvicorn log: `otp_dev_only=XXXXXX` |
| **MSG91 (after DLT)** | `MSG91_ENABLED=true` + auth key + template id | SMS on phone; API may return `sms_provider: msg91` |

**ngrok is not required for OTP** — only Razorpay webhooks use HTTPS tunnel.

### E2E UI — OTP / SMS tab (v5)

Open **http://127.0.0.1:8765** → tab **OTP / SMS**:

1. Header shows FAST2SMS / MSG91 status from `/test-env.json`
2. **FAST2SMS direct** — enter phone → sends via `/test-fast2sms.json` (vendor API only)
3. **Via API** — Request OTP → status shows `sms_provider` (fast2sms / msg91 / dev)
4. Verify → token shared with Customer / Partner tabs

Verify version: http://127.0.0.1:8765/e2e-ui-version.json → `"version": "7"`

---

## Admin tab (Phase 4 — TOTP, v6)

Admin staff **cannot** use SMS OTP (`app_context=admin` is blocked on `/auth/otp/verify`).
Use the **Admin** tab instead.

### One-time setup

1. Add `TOTP_ENC_KEYS` to `.env` (must match what uvicorn loads):

   ```powershell
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

2. Restart uvicorn after changing `.env`.

3. Bootstrap the first admin (prints secret + `otpauth://` once):

   ```powershell
   python scripts/bootstrap_admin.py --phone +919111111100 --name "Dev Admin"
   ```

### Login options (pick one)

| Method | Steps |
|---|---|
| **Google Authenticator / Authy** | Scan the `otpauth://` URI (or enter secret manually) → type the 6-digit code in the UI |
| **Dev helper (no app)** | Paste the bootstrap secret into **Dev only — bootstrap secret** → **Fill current code (dev)** → **Login** |

The dev helper uses Web Crypto HMAC-SHA1 (same RFC 6238 algorithm as the API). Codes expire every 30s.

### What you can exercise on the Admin tab

| Action | API |
|---|---|
| Login | `POST /admin/auth/login` |
| Read advance amount | `GET /admin/settings/advance-booking-amount` |
| Update advance (admin role) | `PUT /admin/settings/advance-booking-amount` |
| Lookup user by phone | `GET /test-user.json?phone=…` (test server only) |
| Assign / list / revoke roles | `POST/GET/DELETE /admin/users/{id}/roles` |
| Provision TOTP credential | `POST /admin/users/{id}/credential` |

### Catalogue media — S3 `.env` (Wave 2)

All storage settings come from `.env` — restart uvicorn after changes.

| Variable | Purpose |
|---|---|
| `S3_ACCESS_KEY` / `S3_SECRET_KEY` | IAM user credentials |
| `S3_REGION` | Must match bucket region (e.g. `ap-south-2`) |
| `S3_BUCKET_CATALOG` | Bucket name only |
| `S3_ENDPOINT_URL` | Leave **empty** for AWS; set only for R2/MinIO (no inline `#` comments) |
| `S3_CATALOG_PUBLIC_URL` | Bucket/CDN base URL — no `catalog/` suffix (object keys already include it) |

**IAM minimum** — `s3:PutObject`, `s3:HeadObject` on `arn:aws:s3:::YOUR_BUCKET/catalog/*`.
`AccessDenied` on upload = IAM policy gap (presign can still return 201).

E2E uploads via **API proxy** (`PUT /admin/catalog/media/{id}/upload`) — no bucket CORS needed.

### Catalogue smoke (4B Wave 1, v9)

After TOTP login, scroll to **Catalogue (4B Wave 1)**:

| Action | API |
|---|---|
| **Run full catalogue smoke** | Chains create/list/update for categories, pujas, content, addons; asserts duplicate category → 409 |
| **Presign → Upload (API) → Confirm** | presign → `PUT .../media/{id}/upload` (proxy) → confirm |
| Categories | `GET/POST/PUT /admin/catalog/categories` |
| Pujas | `GET/POST/PUT /admin/catalog/pujas`, `GET .../impact` |
| Content | `GET/PUT /admin/catalog/pujas/{id}/content` (replace-all `inclusion`) |
| Addons | `GET/POST /pujas/{id}/addons`, `PUT /addons/{id}` |

**Automated (optional):** with uvicorn running and bootstrap admin credentials in env:

```powershell
$env:ADMIN_TEST_PHONE="+919111111100"
$env:ADMIN_TOTP_SECRET="<secret from bootstrap_admin.py>"
pytest tests/test_admin_catalog_live.py -q
```

**Role notes:** `support` can read most admin endpoints; writes (role assign, credential provision, PUT settings) require the `admin` role.

### Windows uvicorn note

If admin login returns 500 / database error, start uvicorn with the selector event loop:

```powershell
python -c "import asyncio; asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy()); import uvicorn; uvicorn.run('app.main:app', host='127.0.0.1', port=8000, reload=True)"
```

---

### CLI smoke (`tests/e2e_ui/otp_smoke.py`)

```powershell
python tests/e2e_ui/otp_smoke.py request --phone +919876543210
python tests/e2e_ui/otp_smoke.py verify --phone +919876543210 --otp 123456
```

### Pytest live (skips if uvicorn not running)

```powershell
# API on :8000
pytest tests/test_otp_live_integration.py -q

# Assert MSG91 actually sent (real phone in OTP_TEST_PHONE):
$env:OTP_TEST_PHONE="+919876543210"
$env:OTP_REQUIRE_MSG91="1"
pytest tests/test_otp_live_integration.py -q -k msg91

# After request + OTP from SMS or log:
$env:OTP_TEST_PHONE="+910000000001"
$env:OTP_TEST_OTP="123456"
pytest tests/test_otp_live_integration.py -q -k verify
```

---

## Razorpay webhook paths

| Mode | How payment confirms |
|---|---|
| **Mock webhook** (button in UI) | Signs payload with your `RAZORPAY_WEBHOOK_SECRET` — good for localhost |
| **Real Razorpay** | ngrok URL in dashboard → `https://….ngrok-free.dev/v1/webhooks/razorpay` |

## Isolation guarantee

- All files live under `tests/e2e_ui/`
- `serve.py` is not imported by `app/`
- pytest does not collect this folder as tests (no `test_*.py` here)

---

## Razorpay + ngrok — full E2E (real payment + real webhook)

### Architecture (what talks to what)

```
Browser (E2E UI :8765)
    │  OTP, booking, Razorpay checkout.js
    ▼
serve.py proxy → API (:8000)
    │
Razorpay Checkout (browser popup) → Razorpay test servers
    │
Razorpay webhook (HTTPS) → ngrok FQDN → localhost:8000/v1/webhooks/razorpay
    │
Celery worker → dispatch → Partner offers
```

**Important:** ngrok tunnels **port 8000 (API)**, not 8765 (test UI). The UI stays on your laptop; only Razorpay’s webhook needs a public URL.

---

### Step 0 — One-time `.env` (project root)

```env
DEBUG=true
SECRET_KEY=<32+ random chars>
DATABASE_URL=postgresql+psycopg://...
REDIS_URL=redis://...

RAZORPAY_KEY_ID=rzp_test_xxxxxxxx
RAZORPAY_KEY_SECRET=your_test_secret
RAZORPAY_WEBHOOK_SECRET=choose_any_secret_string_for_dev
```

| Variable | Where to get it |
|---|---|
| `RAZORPAY_KEY_ID` / `SECRET` | [Razorpay Dashboard](https://dashboard.razorpay.com/) → **Test Mode** → Settings → API Keys |
| `RAZORPAY_WEBHOOK_SECRET` | You choose this (Step 4 below); must match dashboard **and** `.env` |

Never commit `.env` or paste secrets in chat.

---

### Step 1 — Seed DB (once per dev DB)

```powershell
cd C:\OM\Guruji\mana_guruji\puja_platform
.\.venv\Scripts\activate
python tests/e2e_ui/ensure_seed.py
```

---

### Step 2 — Start 4 processes (4 terminals)

**Terminal 1 — API**

```powershell
cd C:\OM\Guruji\mana_guruji\puja_platform
.\.venv\Scripts\activate
uvicorn app.main:app --reload --port 8000
```

**Terminal 2 — Celery** (dispatch after webhook)

```powershell
celery -A app.workers.celery_app worker --pool=solo -Q dispatch,sweep,refund,notifications
```

**Terminal 3 — ngrok → API port 8000**

```powershell
ngrok http 8000
```

Copy the **HTTPS** URL, e.g. `https://wolf-robbing-slideshow.ngrok-free.dev`

**Terminal 4 — E2E test UI**

```powershell
python tests/e2e_ui/serve.py
```

Open **http://127.0.0.1:8765**

---

### Step 3 — E2E UI settings panel

| Field | Value |
|---|---|
| API proxy base | `/proxy/v1` (leave as-is) |
| **Razorpay Key ID** | `rzp_test_…` (same as `.env` — public key, safe in UI) |
| Webhook secret | Optional if using **real** ngrok webhook; required only for **Mock payment webhook** button |

Click **Check API health** → expect `"status":"ok"`.

---

### Step 4 — Razorpay Dashboard webhook (Test Mode)

1. [Razorpay Dashboard](https://dashboard.razorpay.com/) → toggle **Test Mode** (top)
2. **Settings → Webhooks → + Add New Webhook**
3. **Webhook URL:**

   ```text
   https://YOUR-NGROK-SUBDOMAIN.ngrok-free.dev/v1/webhooks/razorpay
   ```

   Example: `https://wolf-robbing-slideshow.ngrok-free.dev/v1/webhooks/razorpay`

4. **Alert email:** your email
5. **Active events:** enable **`payment.captured`** (optional: `order.paid`)
6. **Secret:** enter a string (e.g. `my_local_webhook_secret_123`)
7. Save → put the **same secret** in `.env` as `RAZORPAY_WEBHOOK_SECRET`
8. **Restart uvicorn** if you changed `.env`

---

### Step 5 — Customer flow (UI)

1. **Customer tab** → phone `+910000000001` → Request OTP
2. Copy OTP from **Terminal 1 (uvicorn)** log: `otp_dev_only=XXXXXX`
3. Verify → Create address → Load pujas → Slot hold → **POST /bookings**
4. Click **Razorpay Pay (test)**

**Razorpay test card (success):**

| Field | Value |
|---|---|
| Card | `4111 1111 1111 1111` |
| Expiry | any future date |
| CVV | any 3 digits |
| OTP (3DS) | `1234` or Razorpay test OTP |

5. After payment popup succeeds, Razorpay sends webhook → ngrok → your API
6. **Log tab:** booking status should move toward `requested` after webhook
7. Watch **ngrok inspector:** http://127.0.0.1:4040 → POST `/v1/webhooks/razorpay` should be **200**

---

### Step 6 — Partner flow (UI)

1. Run `ensure_seed.py` if not done
2. **Partner tab** → phone **`+910000000011`** → OTP → Verify
3. **Heartbeat** → should return `ok` (not 403)
4. **GET /offers** → should show offer after customer payment + dispatch
5. **Accept offer**

---

### Troubleshooting

| Symptom | Fix |
|---|---|
| Payment OK but booking stuck `payment_pending` | Webhook not reaching API — check ngrok URL in dashboard, secret match, uvicorn logs |
| ngrok 502 on webhook | uvicorn not running on :8000 |
| Razorpay popup fails | Wrong `RAZORPAY_KEY_ID` in UI; order expired (hold 15 min) |
| 403 heartbeat | Wrong partner phone — use `+910000000011` after `ensure_seed.py` |
| Empty offers | Celery not running; pujari not heartbeat; payment webhook not processed |
| ngrok URL changed | Free plan gets new URL each restart — **update Razorpay webhook URL** |
| Invalid webhook signature | `RAZORPAY_WEBHOOK_SECRET` mismatch between dashboard and `.env` |

---

### Mock webhook vs real Razorpay (pick one)

| Mode | When to use |
|---|---|
| **Razorpay Pay** + ngrok webhook | Full real path; tests Razorpay + signature + dispatch |
| **Mock payment webhook** button | No ngrok; paste `RAZORPAY_WEBHOOK_SECRET` in UI; skips Razorpay popup |

You can use both: Razorpay for checkout UX, mock if webhook debugging is needed.

---

### ngrok free plan notes

- URL changes when you restart ngrok → update Razorpay webhook URL each time
- Keep ngrok terminal open during testing
- Inspector at http://127.0.0.1:4040 shows every webhook attempt and response

