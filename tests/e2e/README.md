# E2E live vendor tests (tests/e2e only)

Manual / CI smoke tests against real SMS providers. **Not part of the product.**

---

## Sprint 1 — booking_fee settlement contract (tests/e2e)

Defines the launch-lite money model **before** migration 025 / `app/` changes ship.

```powershell
cd C:\OM\Guruji\mana_guruji\puja_platform
pytest tests/e2e/test_booking_fee_launch_e2e.py -q
```

| Module | Role |
|---|---|
| `tests/e2e/booking_fee_model.py` | Pure settlement math (no app imports) |
| `tests/e2e/test_booking_fee_launch_e2e.py` | 18 launch-gate scenarios as contract tests |
| `tests/e2e_ui/sprint1_settlement.py` | E2E UI + `/test-sprint1-*.json` endpoints |

E2E UI: **Sprint 1 — Settlements** tab at http://127.0.0.1:8765

---

## FAST2SMS — verify API key in `.env`

### Prerequisites

- `FAST2SMS_API_KEY` in project `.env` (Dev API section of FAST2SMS dashboard)
- Your real mobile in `OTP_TEST_PHONE` for tests that send SMS

### Option A — Direct vendor (fastest, no uvicorn)

Confirms the API key and credits at FAST2SMS only:

```powershell
cd C:\OM\Guruji\mana_guruji\puja_platform
$env:OTP_TEST_PHONE="+91XXXXXXXXXX"
pytest tests/e2e/test_fast2sms_live.py -q -k direct
```

Or CLI:

```powershell
python tests/e2e/fast2sms_smoke.py direct --phone +91XXXXXXXXXX
```

You should receive an OTP SMS on your phone. The script prints the OTP value for reference.

### Option B — Full API stack

Confirms uvicorn → `sms_router` → FAST2SMS:

```powershell
# Terminal 1
uvicorn app.main:app --reload --port 8000

# Terminal 2
$env:OTP_TEST_PHONE="+91XXXXXXXXXX"
$env:OTP_REQUIRE_FAST2SMS=1
pytest tests/e2e/test_fast2sms_live.py -q -k api
```

Or CLI:

```powershell
python tests/e2e/fast2sms_smoke.py api --phone +91XXXXXXXXXX
```

Expected API response:

```json
{
  "status": "otp_sent",
  "sms_sent": true,
  "sms_provider": "fast2sms"
}
```

### Recommended `.env` while MSG91 DLT is pending

```bash
SMS_PROVIDER_ORDER=fast2sms,msg91
MSG91_ENABLED=false
FAST2SMS_API_KEY=your_key_here
```

### Troubleshooting

| Symptom | Check |
|---|---|
| `return: false` from FAST2SMS | Dashboard credits, route `otp`, valid API key |
| `sms_sent: false` via API | Restart uvicorn after `.env` change; check logs for `fast2sms_rejected` |
| Wrong provider | `SMS_PROVIDER_ORDER` must start with `fast2sms`; `MSG91_ENABLED=false` |

---

## Setu DigiLocker KYC — partner onboarding (migration 020)

Manual / CI smoke for **real Setu sandbox** + your running API. Completing DigiLocker in the browser is required for full finalize (cannot be fully headless).

### Prerequisites

1. **Migration 020** applied: `python scripts/apply_migration_020.py`
2. **Migration 023** applied: `python scripts/apply_migration_023.py` (selfie `uploading` status)
3. **Uvicorn** on `:8000` for `api` mode
3. **Redis** reachable (`REDIS_URL`) — poll finalize uses a short NX lock
4. **Public callback URL** — Setu redirects the browser to your API; localhost alone will not work for real consent. Use **ngrok** (or similar) pointing at `http://127.0.0.1:8000`

### `.env` — KYC block (copy into project `.env`)

```bash
# ---- Partner KYC (Setu DigiLocker sandbox) -------------------------------
KYC_VENDOR=setu_digilocker

# MUST be publicly reachable. Register this EXACT URL in Setu Bridge (no query string).
# ngrok example (replace with your subdomain):
KYC_REDIRECT_URL=https://YOUR-SUBDOMAIN.ngrok-free.app/v1/pujari/kyc/callback

# Where the callback redirects the user after Setu (deep link or web page)
KYC_APP_RETURN_URL=managuruji://kyc/complete

# Random secret — never commit. Generate once:
#   python -c "import secrets; print(secrets.token_hex(32))"
KYC_IDENTITY_PEPPER=your_64_char_hex_here

KYC_REQUEST_TTL_MINUTES=30
KYC_RETENTION_DAYS=365

# Setu sandbox (from Setu Bridge → DigiLocker product → Credentials)
KYC_SETU_BASE_URL=https://dg-sandbox.setu.co
KYC_SETU_CLIENT_ID=your_client_id
KYC_SETU_CLIENT_SECRET=your_client_secret
KYC_SETU_DIGILOCKER_PRODUCT_ID=your_product_instance_id

# Optional — PAN product (Phase 4; not needed for Aadhaar E2E)
# KYC_SETU_PAN_PRODUCT_ID=
```

Also required for **full API E2E** (same as other flows):

```bash
SECRET_KEY=...                    # min 32 chars (already in your .env)
DATABASE_URL=postgresql+psycopg://...
REDIS_URL=redis://localhost:6379/0
DEBUG=true                      # otp_dev_only in uvicorn log (no SMS needed)

# Selfie upload step (optional for DigiLocker-only smoke)
S3_ACCESS_KEY=...
S3_SECRET_KEY=...
S3_BUCKET_KYC=puja-kyc-docs
# S3_ENDPOINT_URL=...           # MinIO/R2 if not AWS
```

E2E test overrides (optional):

```bash
E2E_API_UPSTREAM=http://127.0.0.1:8000
KYC_TEST_PHONE=+917675834207    # pujari OTP phone for api smoke
KYC_TEST_OTP=123456             # skip prompt if you already have OTP
KYC_E2E_POLL_TIMEOUT_S=300      # seconds to wait after opening DigiLocker URL
```

### Setu Bridge — redirect URL rules

| Rule | Detail |
|------|--------|
| Register in Setu | The **base** callback URL only — e.g. `https://abc.ngrok-free.app/v1/pujari/kyc/callback` |
| No trailing slash mismatch | Must match `KYC_REDIRECT_URL` character-for-character |
| Query params | Setu appends `success`, `id`, `scope`, `errCode`; your app appends `kyc_nonce` when calling Setu — both are supported |
| Sandbox Aadhaar | Use test Aadhaar `999999990019` per Setu docs |

### ngrok quick setup

```powershell
# Terminal 1 — API
cd C:\OM\Guruji\mana_guruji\puja_platform
uvicorn app.main:app --reload --port 8000

# Terminal 2 — tunnel (install ngrok if needed)
ngrok http 8000
```

Copy the `https://....ngrok-free.app` host into:

```bash
KYC_REDIRECT_URL=https://YOUR-ID.ngrok-free.app/v1/pujari/kyc/callback
```

Register that same URL in Setu Bridge, restart uvicorn after `.env` change.

### Option A — Direct Setu (fastest, no uvicorn)

Confirms `KYC_SETU_*` credentials and product instance id:

```powershell
cd C:\OM\Guruji\mana_guruji\puja_platform
python tests/e2e/setu_digilocker_smoke.py direct
```

Or pytest:

```powershell
pytest tests/e2e/test_kyc_digilocker_live.py -q -k direct
```

Expected: HTTP 200 or 201 JSON with `id`, `url`, `validUpto`.

### Option B — Full API stack (register → start → browser → poll)

```powershell
# Terminal 1
uvicorn app.main:app --reload --port 8000

# Terminal 2
$env:DEBUG="true"
$env:KYC_TEST_PHONE="+917675834207"
python tests/e2e/setu_digilocker_smoke.py api --phone +917675834207
```

Flow:

1. Script requests OTP → copy `otp_dev_only` from uvicorn log (or set `KYC_TEST_OTP`)
2. `POST /pujari/register` + `POST /pujari/kyc/digilocker`
3. Open printed DigiLocker URL → consent with sandbox Aadhaar `999999990019`
4. Script polls `GET /pujari/kyc/requests/{id}` until `status=success`

Optional next steps (manual):

- `python tests/e2e/setu_digilocker_smoke.py api-full` — DigiLocker + selfie + admin approve → `verified`
  (needs `S3_BUCKET_KYC`, `ADMIN_TEST_PHONE`, `ADMIN_TOTP_SECRET`)

### Full backend E2E (`api-full`)

```powershell
$env:ADMIN_TEST_PHONE="+919111111100"
$env:ADMIN_TOTP_SECRET="<from bootstrap_admin.py>"
python tests/e2e/setu_digilocker_smoke.py api-full --phone +917675834207
```

After DigiLocker success the script uploads a minimal JPEG selfie, confirms it, approves all
three doc types via admin TOTP, and prints `verification_status=verified`.

### Selfie-only E2E (no DigiLocker — fast gate before Flutter)

Use this to validate presign → S3 PUT → confirm + EXIF strip without opening DigiLocker.

**Pytest (7 cases):**

```powershell
# Terminal 1
uvicorn app.main:app --reload --port 8000

# Terminal 2
$env:DEBUG="true"
pytest tests/e2e/test_kyc_selfie_live.py -q -s
```

Covers: happy path, confirm-without-upload (422), unknown doc (404), EXIF strip (S3 fetch),
invalid content-type (422), second presign replaces current doc, idempotent re-confirm.

**CLI smoke:**

```powershell
python tests/e2e/kyc_selfie_smoke.py
python tests/e2e/kyc_selfie_smoke.py --exif   # EXIF strip check
python tests/e2e/kyc_selfie_smoke.py --phone +917675834207
```

Requires `S3_BUCKET_KYC` + IAM credentials (same as DigiLocker finalize).

### Troubleshooting

| Symptom | Check |
|---------|--------|
| Setu 401/403 | `KYC_SETU_CLIENT_ID/SECRET` and `KYC_SETU_DIGILOCKER_PRODUCT_ID` (product instance id header) |
| `KYC redirect URL is not configured` | `KYC_REDIRECT_URL` empty — restart uvicorn |
| Callback 403 invalid nonce | `KYC_IDENTITY_PEPPER` changed mid-flight; start a new DigiLocker request |
| Poll stuck at `created` | Complete DigiLocker in browser; ensure ngrok URL matches Setu registration |
| `httpx.ReadTimeout` on `direct` | Setu sandbox hung — often **wrong product instance id** (PAN id in DigiLocker field) or sandbox outage; run `python tests/e2e/setu_digilocker_smoke.py auth` |
| HTTP **504** `upstream server is timing out` | Setu received your call (auth OK) but DigiLocker bridge not ready — complete **Resume configuration** in Bridge until status is not **KYC INCOMPLETE** |
| Fast 401 on `auth` probe 1 | Expected; probe 2 uses your real creds |
| Redis timeout on poll | `REDIS_URL` reachable from API process |
| Poll **500** / **502** `KYC document storage unavailable` | DigiLocker consent succeeded; S3 upload failed. Set real `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET_KYC` (and `S3_REGION`). Restart uvicorn, then re-run `api` — finalize retries. |
| Selfie step fails | Same S3 vars as above |
