# Dev merge → CI → staging deploy checklist

SSOT: [`STAGING_DEPLOY_PIPELINE.md`](./STAGING_DEPLOY_PIPELINE.md), [`DEVELOPER_RELEASE_FLOW.md`](./DEVELOPER_RELEASE_FLOW.md)

## What runs on `git push origin dev`

| Step | Workflow | What it does |
|------|-----------|----------------|
| 1 | [`ci.yml`](../../.github/workflows/ci.yml) | **Linux arm64** `pip install -r requirements.txt` + `verify_linux_runtime.py`; **G1–G3** via `deploy_preflight_repo.py` |
| 2 | [`deploy-staging.yml`](../../.github/workflows/deploy-staging.yml) | If changed paths match → SSH/self-hosted **`remote_staging_deploy.sh`** |

**Path filters for staging deploy** (backend only): `app/**`, `scripts/**`, `spec/db/**`, `admin_ui/**`, `requirements.txt`, etc.  
**Not auto-deployed:** `mana_guruji_mobile/**` (separate store/build pipeline).

## Full staging deploy (`component=full`, default on push)

1. `git checkout -B deploy-staging origin/dev`
2. `bootstrap_python_runtime.sh` — **pip / binaries** from `requirements.txt`
3. **`migrate.sh`** — `alembic upgrade head` → **`run_sql_migrations.py`** (includes **`apply_migration_040.py`** when on disk) → `apply_grants.py`
4. **`systemctl restart`** `mana-guruji-api`, `mana-guruji-celery-worker`, `mana-guruji-celery-beat`
5. Rebuild **admin** Next.js if `admin.env` exists

## Verify after merge (Track B example)

```bash
# GitHub Actions: Deploy staging — green job
# VM:
curl -fsS http://127.0.0.1:8000/health/live
cd /opt/mana-guruji/src/puja_platform && git rev-parse HEAD  # = origin/dev
# Optional:
python scripts/verify_database_schema.py --strict --label staging
```

## PR order for partner UX work

1. Merge **`bug/dispatch-offer-rounds` (#22)** → `dev` first (if still open).
2. PR **`feature/urgency-flip-rebroadcast`** → `dev` (migration **040** lands via `migrate.sh`).
3. PR **`feature/partner-background-presence`** → `dev` (API + Flutter; ship partner APK with B6 from Track B).
4. Restart Celery after each backend merge (deploy script does on staging).

## G3 migration gate

New `scripts/apply_migration_*.py` files must be discoverable by `sql_migrate_manifest.py` (no manual list edit).  
Local check: `python scripts/deploy_preflight_repo.py`

## Render blueprint (`render.yaml`)

Separate **dev** stack on **`main`** branch — **not** the OCI staging CD path above. Do not confuse Render with `stg-aio-1`.