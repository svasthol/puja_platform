# Staging environment variables — complete reference

**Loaded by:** `app/core/config.py` → `Settings` (from `/etc/mana-guruji/api.env` on VM).  
**Template:** `deploy/env/staging.api.env.example`  
**Validate on VM:** `python scripts/validate_api_env.py /etc/mana-guruji/api.env --strict-staging`  
**Rollout order:** [`STAGING_CONFIG_ROLLOUT.md`](./STAGING_CONFIG_ROLLOUT.md)

**Ops-only (in `api.env`, not in `Settings`):** `DATABASE_MIGRATE_URL`, `DATABASE_ADMIN_URL`  
**Admin UI:** `/etc/mana-guruji/admin.env` → `NEXT_PUBLIC_API_URL` only (rebuild after change).

**Not in env (Postgres / Admin UI):** `platform_settings` (booking fee, night gate, dispatch, `kyc_vendor` override, TDS facilitation JSON), `tax_statutory_config`.

---

## KYC (Setu + API Sathi)

| Variable | Staging notes |
|----------|----------------|
| `KYC_VENDOR` | Default when console unset. Staging: `apisathi` or `setu_digilocker`. |
| `KYC_REDIRECT_URL` | Public HTTPS callback; **no** query string. |
| `KYC_APP_RETURN_URL` | `managuruji://kyc/complete` |
| `KYC_IDENTITY_PEPPER` | Stable per DB; `openssl rand -hex 32` |
| `KYC_APISATHI_BASE_URL` | `https://apisathi.in/gw/v1` |
| `KYC_APISATHI_API_KEY` | `test_…` or `live_…`; required if vendor = apisathi |
| `KYC_APISATHI_READ_TIMEOUT` | default `25` |
| `KYC_SETU_*` | Sandbox IDs; required if vendor = setu or admin switch back |
| `KYC_VENDOR_STATUS_POLL_MIN_SECONDS` | default `15` |

Admin **Settings → KYC vendor** picks active vendor for **new** requests; env must include credentials for any vendor you allow switching to.

---

## All `Settings` keys (grouped)

### Application

| Variable | Default |
|----------|---------|
| `APP_ENV` | development |
| `APP_NAME` | Puja Booking Platform |
| `DEBUG` | false |
| `SECRET_KEY` | *(required, ≥32)* |
| `API_V1_PREFIX` | /v1 |
| `ALLOWED_ORIGINS` | localhost:3000, 127.0.0.1:3000 |
| `PLATFORM_TIMEZONE` | Asia/Kolkata |

### Database & Redis

| Variable | Default |
|----------|---------|
| `DATABASE_URL` | *(required)* |
| `DATABASE_POOL_SIZE` | 10 |
| `DATABASE_MAX_OVERFLOW` | 5 |
| `DATABASE_POOL_RECYCLE` | 1800 |
| `REDIS_URL` | redis://localhost:6379/0 — **path must be /0** |
| `REDIS_DB_CACHE` | 0 |
| `REDIS_DB_CELERY` | 1 |
| `REDIS_DB_PRESENCE` | 2 |

### Auth & admin TOTP

| Variable | Default |
|----------|---------|
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 60 |
| `REFRESH_TOKEN_EXPIRE_DAYS` | 30 |
| `OTP_EXPIRE_MINUTES` | 10 |
| `OTP_MAX_ATTEMPTS` | 5 |
| `OTP_RATE_LIMIT_PER_HOUR` | 3 |
| `OTP_RESEND_COOLDOWN_SECONDS` | 20 |
| `ADMIN_ACCESS_TOKEN_EXPIRE_MINUTES` | 30 |
| `ADMIN_REFRESH_TOKEN_EXPIRE_DAYS` | 1 |
| `ADMIN_LOGIN_RATE_LIMIT_PER_HOUR` | 20 |
| `TOTP_ISSUER` | Mana Guruji |
| `TOTP_STEP_SECONDS` | 30 |
| `TOTP_VERIFY_WINDOW` | 1 |
| `TOTP_ENC_KEYS` | "" |

### Payments & launch

| Variable | Default |
|----------|---------|
| `RAZORPAY_KEY_ID` | "" |
| `RAZORPAY_KEY_SECRET` | "" |
| `RAZORPAY_WEBHOOK_SECRET` | "" |
| `FULL_ONLINE_ENABLED` | false |
| `DEFAULT_ADVANCE_BOOKING_AMOUNT` | 250.0 |
| `DEFAULT_BOOKING_FEE` | 61.0 |
| `DEFAULT_SUPPORT_REFUND_CAP_PER_ACTION` | 5000.0 |
| `DEFAULT_SUPPORT_REFUND_CAP_DAILY` | 20000.0 |

### TDS / PAN (env flags)

| Variable | Default |
|----------|---------|
| `TDS_ACCRUAL_ENABLED` | false |
| `TDS_ACCEPT_STUB_COLLECT` | false |
| `PAN_ACCEPT_GATE_ENABLED` | false |
| `PUJARI_TAX_PROFILE_REQUIRED_FOR_ACCEPT` | false |
| `PUJARI_FY_PAN_GATE_ENABLED` | false |

### SMS

| Variable | Default |
|----------|---------|
| `SMS_PROVIDER_ORDER` | fast2sms,msg91 |
| `MSG91_ENABLED` | false |
| `MSG91_AUTH_KEY` | "" |
| `MSG91_TEMPLATE_ID` | "" |
| `MSG91_TXN_TEMPLATE_ID` | "" |
| `MSG91_SENDER_ID` | PUJAPL |
| `FAST2SMS_API_KEY` | "" |
| `FAST2SMS_OTP_ROUTE` | otp |
| `FAST2SMS_QUICK_ROUTE` | q |

### Storage (S3-compatible)

| Variable | Default |
|----------|---------|
| `S3_ENDPOINT_URL` | "" |
| `S3_REGION` | ap-south-1 |
| `S3_ACCESS_KEY` | "" |
| `S3_SECRET_KEY` | "" |
| `S3_BUCKET_KYC` | puja-kyc-docs |
| `S3_BUCKET_CATALOG` | puja-catalog |
| `S3_CATALOG_PUBLIC_URL` | "" |
| `S3_CATALOG_URL_EXPIRE_SECONDS` | 600 |
| `S3_CATALOG_MAX_BYTES` | 5242880 |
| `S3_KYC_URL_EXPIRE_SECONDS` | 300 |
| `S3_KYC_MAX_BYTES` | 5242880 |

### KYC (see section above)

Also: `KYC_REQUEST_TTL_MINUTES`, `KYC_RETENTION_DAYS`, `KYC_CALLBACK_RATE_LIMIT_PER_HOUR`, `KYC_START_RATE_LIMIT_PER_HOUR`, `KYC_VENDOR_PAN_MIN_INTERVAL_SECONDS`.

### FCM, maps, panchangam, dispatch defaults

| Variable | Default |
|----------|---------|
| `FCM_SERVICE_ACCOUNT_PATH` | "" |
| `FCM_SERVER_KEY` | "" |
| `GOOGLE_MAPS_API_KEY` | "" |
| `SERVICE_BOUNDARY_GEOJSON_PATH` | spec/geo/hyderabad_launch_service.geojson |
| `PANCHANGAM_VENDOR_URL` | "" |
| `PANCHANGAM_API_KEY` | "" |
| `PANCHANGAM_DEFAULT_CITIES` | ["Hyderabad"] |
| `SLOT_HOLD_TTL_MINUTES` | 5 |
| `BOOKING_PAYMENT_TTL_MINUTES` | 15 |
| `DISPATCH_OFFER_TTL_SECONDS` | 120 |
| `DISPATCH_MAX_ROUNDS` | 4 |
| `DISPATCH_RADIUS_KM` | [3,6,10,15] |
| `PUJARI_PRESENCE_TTL_SECONDS` | 90 |
| `PUJARI_PRESENCE_BACKGROUND_TTL_SECONDS` | 600 |
| `WS_TICKET_TTL_SECONDS` | 30 |

### Monitoring

| Variable | Default |
|----------|---------|
| `METRICS_ENABLED` | true |
| `SENTRY_DSN` | "" |
| `MONITOR_PAYMENT_PENDING_GRACE_MINUTES` | 30 |
| `MONITOR_CONFIRMED_NO_SHOW_GRACE_MINUTES` | 90 |
| `MONITOR_REFUND_STALL_ATTEMPTS` | 6 |

Source of truth for defaults: `app/core/config.py`.