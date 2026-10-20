# Staging environment variables — complete reference

**Loaded by:** `app/core/config.py` → `Settings` (from `/etc/mana-guruji/api.env` on VM).  
**Rollout order:** [`STAGING_CONFIG_ROLLOUT.md`](./STAGING_CONFIG_ROLLOUT.md)

Also required on VM for **ops** (not FastAPI): `DATABASE_MIGRATE_URL`, `DATABASE_ADMIN_URL`.  
**Admin UI:** `/etc/mana-guruji/admin.env` → `NEXT_PUBLIC_API_URL` only.

---

## Ops-only (in `api.env`, not in `Settings`)

| Variable | Purpose |
|----------|---------|
| `DATABASE_MIGRATE_URL` | `migrate.sh` / Alembic |
| `DATABASE_ADMIN_URL` | `bootstrap.sh`, `apply_grants.py` |

---

## All `Settings` keys (alphabetical)

| Variable | Default |
|----------|---------|
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 60 |
| `ADMIN_ACCESS_TOKEN_EXPIRE_MINUTES` | 30 |
| `ADMIN_LOGIN_RATE_LIMIT_PER_HOUR` | 20 |
| `ADMIN_REFRESH_TOKEN_EXPIRE_DAYS` | 1 |
| `ALLOWED_ORIGINS` | localhost:3000, 127.0.0.1:3000 |
| `API_V1_PREFIX` | /v1 |
| `APP_ENV` | development |
| `APP_NAME` | Puja Booking Platform |
| `BOOKING_PAYMENT_TTL_MINUTES` | 15 |
| `DATABASE_MAX_OVERFLOW` | 5 |
| `DATABASE_POOL_RECYCLE` | 1800 |
| `DATABASE_POOL_SIZE` | 10 |
| `DATABASE_URL` | *(required)* |
| `DEBUG` | false |
| `DEFAULT_ADVANCE_BOOKING_AMOUNT` | 250.0 |
| `DEFAULT_BOOKING_FEE` | 61.0 |
| `DEFAULT_SUPPORT_REFUND_CAP_DAILY` | 20000.0 |
| `DEFAULT_SUPPORT_REFUND_CAP_PER_ACTION` | 5000.0 |
| `DISPATCH_MAX_ROUNDS` | 4 |
| `DISPATCH_OFFER_TTL_SECONDS` | 120 |
| `DISPATCH_RADIUS_KM` | [3,6,10,15] |
| `FAST2SMS_API_KEY` | "" |
| `FAST2SMS_OTP_ROUTE` | otp |
| `FAST2SMS_QUICK_ROUTE` | q |
| `FCM_SERVER_KEY` | "" |
| `FCM_SERVICE_ACCOUNT_PATH` | "" |
| `FULL_ONLINE_ENABLED` | false |
| `GOOGLE_MAPS_API_KEY` | "" |
| `KYC_APP_RETURN_URL` | managuruji://kyc/complete |
| `KYC_CALLBACK_RATE_LIMIT_PER_HOUR` | 60 |
| `KYC_IDENTITY_PEPPER` | "" |
| `KYC_REDIRECT_URL` | "" |
| `KYC_REQUEST_TTL_MINUTES` | 30 |
| `KYC_RETENTION_DAYS` | 365 |
| `KYC_SETU_BASE_URL` | https://dg-sandbox.setu.co |
| `KYC_SETU_CLIENT_ID` | "" |
| `KYC_SETU_CLIENT_SECRET` | "" |
| `KYC_SETU_DIGILOCKER_PRODUCT_ID` | "" |
| `KYC_SETU_PAN_PRODUCT_ID` | "" |
| `KYC_SETU_READ_TIMEOUT` | 25.0 |
| `KYC_START_RATE_LIMIT_PER_HOUR` | 10 |
| `KYC_VENDOR` | setu_digilocker |
| `METRICS_ENABLED` | true |
| `MONITOR_CONFIRMED_NO_SHOW_GRACE_MINUTES` | 90 |
| `MONITOR_PAYMENT_PENDING_GRACE_MINUTES` | 30 |
| `MONITOR_REFUND_STALL_ATTEMPTS` | 6 |
| `MSG91_AUTH_KEY` | "" |
| `MSG91_ENABLED` | false |
| `MSG91_SENDER_ID` | PUJAPL |
| `MSG91_TEMPLATE_ID` | "" |
| `MSG91_TXN_TEMPLATE_ID` | "" |
| `OTP_EXPIRE_MINUTES` | 10 |
| `OTP_MAX_ATTEMPTS` | 5 |
| `OTP_RATE_LIMIT_PER_HOUR` | 5 |
| `PAN_ACCEPT_GATE_ENABLED` | false |
| `PANCHANGAM_API_KEY` | "" |
| `PANCHANGAM_DEFAULT_CITIES` | ["Hyderabad"] |
| `PANCHANGAM_VENDOR_URL` | "" |
| `PLATFORM_TIMEZONE` | Asia/Kolkata |
| `PUJARI_FY_PAN_GATE_ENABLED` | false |
| `PUJARI_PRESENCE_TTL_SECONDS` | 90 |
| `PUJARI_TAX_PROFILE_REQUIRED_FOR_ACCEPT` | false |
| `RAZORPAY_KEY_ID` | "" |
| `RAZORPAY_KEY_SECRET` | "" |
| `RAZORPAY_WEBHOOK_SECRET` | "" |
| `REDIS_DB_CACHE` | 0 |
| `REDIS_DB_CELERY` | 1 |
| `REDIS_DB_PRESENCE` | 2 |
| `REDIS_URL` | redis://localhost:6379/0 |
| `REFRESH_TOKEN_EXPIRE_DAYS` | 30 |
| `SECRET_KEY` | *(required, ≥32 chars)* |
| `S3_ACCESS_KEY` | "" |
| `S3_BUCKET_CATALOG` | puja-catalog |
| `S3_BUCKET_KYC` | puja-kyc-docs |
| `S3_CATALOG_MAX_BYTES` | 5242880 |
| `S3_CATALOG_PUBLIC_URL` | "" |
| `S3_CATALOG_URL_EXPIRE_SECONDS` | 600 |
| `S3_ENDPOINT_URL` | "" |
| `S3_KYC_MAX_BYTES` | 5242880 |
| `S3_KYC_URL_EXPIRE_SECONDS` | 300 |
| `S3_REGION` | ap-south-1 |
| `S3_SECRET_KEY` | "" |
| `SENTRY_DSN` | "" |
| `SLOT_HOLD_TTL_MINUTES` | 5 |
| `SMS_PROVIDER_ORDER` | fast2sms,msg91 |
| `TDS_ACCEPT_STUB_COLLECT` | false |
| `TDS_ACCRUAL_ENABLED` | false |
| `TOTP_ENC_KEYS` | "" |
| `TOTP_ISSUER` | Mana Guruji |
| `TOTP_STEP_SECONDS` | 30 |
| `TOTP_VERIFY_WINDOW` | 1 |
| `WS_TICKET_TTL_SECONDS` | 30 |

Source of truth for defaults: `app/core/config.py`.
