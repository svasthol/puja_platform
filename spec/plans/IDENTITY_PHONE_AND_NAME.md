# Identity — canonical phone + Aadhaar display name

**Status:** Shipped in `bug/phone-canonical-otp` (2026-10-31).

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
python scripts/dedupe_users_by_canonical_phone.py        # dry-run
python scripts/dedupe_users_by_canonical_phone.py --apply  # merge dupes
```

Review admin **Partners** list; deactivate stray test users manually if both rows had a pujari.

## Prod

Deploy **before** real user onboarding. If duplicates already exist, dry-run → reviewed `--apply` or manual merge — do not skip.
