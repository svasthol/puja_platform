# E2E live vendor tests (tests/e2e only)

Manual / CI smoke tests against real SMS providers. **Not part of the product.**

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
