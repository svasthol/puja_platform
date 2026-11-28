# Apply staging `api.env` (ops — not secrets)

After editing `/etc/mana-guruji/api.env` on **stg-aio-1**:

```bash
sudo nano /etc/mana-guruji/api.env
source /opt/mana-guruji/src/puja_platform/scripts/linux/source_api_env.sh /etc/mana-guruji/api.env
/opt/mana-guruji/venv/bin/python scripts/validate_api_env.py /etc/mana-guruji/api.env --strict-staging
/opt/mana-guruji/venv/bin/python scripts/deploy_preflight_live.py
/opt/mana-guruji/venv/bin/python scripts/verify_staging_storage.py --strict
sudo systemctl restart mana-guruji-api mana-guruji-celery-worker mana-guruji-celery-beat
curl -sS https://api-stg.managuruji.in/v1/app-config | jq '{kyc: .setu_pan_verify_configured, tds_accrual_enabled, payments_enabled}'
```

**Git template:** copy structure from `deploy/env/staging.api.env.example` and paste your real values from the password store.

### Must-fix vs your prior file

| Issue | Fix |
|-------|-----|
| `ALLOWED_ORIGINS='[...]'` | Remove outer single quotes |
| `REDIS_URL=.../2` | `REDIS_URL=.../0` + `REDIS_DB_CACHE=0` `REDIS_DB_CELERY=1` `REDIS_DB_PRESENCE=2` |
| No API Sathi | Add `KYC_VENDOR=apisathi` + `KYC_APISATHI_*` block |
| Missing TDS flags | Add explicit `TDS_*` / `PAN_*` / `PUJARI_*` block |
| `SECRET_KEY=change-me...` | `openssl rand -hex 32` |

Keep **both** Setu and API Sathi credential blocks so Admin → KYC vendor can switch without redeploy.

### Reset staging users (clean slate before prod-like data)

```bash
source /opt/mana-guruji/src/puja_platform/scripts/linux/source_api_env.sh /etc/mana-guruji/api.env
/opt/mana-guruji/venv/bin/python scripts/staging_wipe_users.py --dry-run
/opt/mana-guruji/venv/bin/python scripts/staging_wipe_users.py --confirm-wipe-staging-users
```

Keeps **admin/support** accounts, catalog, and `platform_settings`. Removes bookings + non-staff users (cascades pujaris, KYC rows, devices, addresses).

Only verified partners: `--scope verified-partners`