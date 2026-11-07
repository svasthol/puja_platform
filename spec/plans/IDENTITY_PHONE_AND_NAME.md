# Identity — canonical phone + Aadhaar display name

**Status:** Merged to **`dev`** (puja_platform PR #7, Flutter PR #1, 2026-11-01). Sign-off: [`KYC_SETU_SANDBOX_STATUS.md`](./KYC_SETU_SANDBOX_STATUS.md).

## Problem

- OTP stored `users.phone` **verbatim** → `9515165674` and `+919515165674` were two users.
- New OTP users got `full_name = "New User"`; Aadhaar legal name was never copied to `users.full_name`.

## Canonical phone

| Storage | Format | Example |
|---------|--------|---------|
| `users.phone` | E.164 India | `+919515165674` |
| OTP rows / rate limits | Same | Same |
| SMS providers | Existing `normalize_india_mobile_*` | Derived from same 10-digit core |

**Code:** `app/services/sms_phone.py` → `canonical_user_phone()`  
**Validated on:** `OtpRequest`, `OtpVerify`, `AdminLoginRequest` (Pydantic)  
**Flutter:** `lib/core/phone/india_phone.dart` → `canonicalIndiaPhoneForApi()`

## Display name from Aadhaar

On successful DigiLocker Aadhaar fetch (`partner_kyc_service` ingest):

- If `users.full_name` is placeholder (**"New User"**) → set to Aadhaar `identity.name` (trim, max 150).
- Else if registered name ≠ Aadhaar (normalized) → `name_mismatch` review flag (unchanged).

## Staging cleanup (test data)

After deploying this change:

```bash
cd /opt/mana-guruji/src/puja_platform
source /opt/mana-guruji/venv/bin/activate
set -a && source /etc/mana-guruji/api.env && set +a
python scripts/dedupe_users_by_canonical_phone.py        # dry-run (DATABASE_URL)
python scripts/dedupe_users_by_canonical_phone.py --apply  # needs DATABASE_MIGRATE_URL in api.env
```

Review admin **Partners** list. **`--apply`** tombstones orphan `users.phone` to **`+8` + 13 hex** (15 chars max; frees the unique key), sets survivor to `+91…`, and deletes an orphan **pending** pujari when the survivor is **verified** (both had profiles). Other “both pujari” cases still need manual review.

## Prod

Deploy **before** real user onboarding. If duplicates already exist, dry-run → reviewed `--apply` or manual merge — do not skip.
