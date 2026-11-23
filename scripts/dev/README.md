# Dev-only database scripts

**Do not run against staging or production.** These scripts **delete** customer booking data.

| Script | Purpose |
|--------|---------|
| `clean_dev_bookings.sql` | `TRUNCATE` bookings, payments, assignments, dispatch state, related rows (keeps users, pujaris, catalog). |
| `run_clean_dev_bookings.py` | Applies the SQL via app DB config; optionally `FLUSHDB` on cache/celery/presence Redis. |

## Safety gates (`run_clean_dev_bookings.py`)

- **`APP_ENV` must be `development`**. Refuses `staging` and `production`.
- Requires CLI flag **`--confirm-wipe-bookings`** (no accidental runs).
- Use **`--no-redis`** to skip Redis flush.

```powershell
cd puja_platform
$env:APP_ENV = "development"
python scripts/dev/run_clean_dev_bookings.py --confirm-wipe-bookings
```

Raw SQL (only when you know the target DB is local dev):

```bash
psql -d Mana_Guruji -f scripts/dev/clean_dev_bookings.sql
```

After Redis flush: restart Celery **worker** and **beat**.