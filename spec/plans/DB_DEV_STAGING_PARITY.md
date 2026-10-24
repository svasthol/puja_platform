# Dev ↔ Staging PostgreSQL parity (compare + safe sync)

**Goal:** Prove **structure** on laptop dev DB matches **staging** (`Mana_Guruji`) without copying data or applying ad-hoc DDL from dev.

## Staging Postgres access (SSH tunnel — recommended)

On `stg-aio-1`, PostgreSQL listens on **`127.0.0.1:5432`** only. It is **not** meant to be reachable as `140.245.245.201:5432`, even if OCI/firewalld allow 5432.

**Best practice:** SSH local forward (what you already do):

```powershell
ssh -L 15432:127.0.0.1:5432 opc@140.245.245.201
```

Or:

```powershell
.\scripts\windows\Start-StagingDbTunnel.ps1
# or: python scripts/staging_db_tunnel.py
```

Then connect with:

```text
postgresql://puja_migrate:PASSWORD@127.0.0.1:15432/Mana_Guruji
```

| Approach | Verdict |
|----------|---------|
| `ssh -L 15432:127.0.0.1:5432` + `127.0.0.1:15432` | **Use this** — secure, matches VM config |
| Public `:5432` on VM IP | **Not required** — avoid opening Postgres on the internet |
| Terraform `developer_tcp_ports` | Default **8000, 3000, 6379** only (no 5432) |

Self-hosted staging runner (GitHub on VM) uses `localhost:5432` directly — no tunnel.

## What is compared (read-only)

When compare prints **OK**, every row in the **parity coverage** summary matched exactly between dev and staging (not just table count).

| Layer | What equality means |
|--------|---------------------|
| **Columns** | Per table: name, `udt_name`, nullable, default, ordinal position |
| **PRIMARY KEY** | Same `pg_get_constraintdef` (column set) |
| **UNIQUE** | Same unique definitions |
| **FOREIGN KEY** | Same FK targets and columns |
| **CHECK / EXCLUDE** | Same check/exclusion expressions (internal `NOT NULL` checks skipped) |
| **Indexes** | Same index definition (ignores index *name*) |
| **Triggers** | Same `table.trigger` names |
| **Sequences** | Same sequence parameters |
| **Extensions** | Same extension *names* (version mismatch = warning only) |
| **Alembic** | Same `version_num` |
| **Spec** | `verify_database_schema.py` vs `spec/db` |

### Export full inventories (every column listed)

```powershell
python scripts/compare_database_schemas.py `
  --left-url $env:DEV_DATABASE_URL --left-label dev `
  --right-url $env:STAGING_DATABASE_URL --right-label staging `
  --inventory-md dev_schema.md staging_schema.md
```

Or JSON catalogs: `--export-catalogs dev_catalog.json staging_catalog.json`

## What is **not** done (safety)

- No `pg_dump` schema from dev → staging
- No `DROP TABLE` / `ALTER` generated from diff
- No row data sync
- **Allowed fix on staging:** repo `scripts/migrate.sh` only (Alembic + `012`–`034` + `apply_grants.py`)

## Laptop pipeline (recommended)

```powershell
cd C:\OM\Guruji\mana_guruji\puja_platform
.\.venv\Scripts\Activate.ps1

$env:DEV_DATABASE_URL = "postgresql://postgres@127.0.0.1:5432/Mana_Guruji"
$env:STAGING_DATABASE_URL = "postgresql://puja_migrate:YOUR_PASSWORD@127.0.0.1:15432/Mana_Guruji"

.\scripts\windows\Run-DbDevStagingParity.ps1 -EnsureTunnel -Compare -Strict
```

`-EnsureTunnel` runs `ssh -f -N -L 15432:127.0.0.1:5432` if the port is not already open.

Optional: `-UpdateIngress` only if you need **API :8000** / admin **:3000** from a new laptop IP (not for DB).

```powershell
python scripts/db_dev_staging_parity.py --ensure-tunnel --compare --strict
```

Legacy URLs with `@140.245.245.201:5432` are **rewritten** to `127.0.0.1:15432` when passed through the parity script (tunnel must be up).

### After drift is found (safe sync)

```powershell
python scripts/db_parity_sync.py --dev-url $env:DEV_DATABASE_URL --staging-url $env:STAGING_DATABASE_URL --action plan

# migrate on VM (SSH) — does not need DB tunnel from laptop
python scripts/db_parity_sync.py --dev-url $env:DEV_DATABASE_URL --staging-url $env:STAGING_DATABASE_URL --action staging-migrate --yes
```

Or GitHub Actions → **DB dev staging parity** → **staging_migrate** (self-hosted VM).

## GitHub Actions

| Workflow | Use |
|----------|-----|
| [`db-verify.yml`](../../.github/workflows/db-verify.yml) | Staging vs `spec/db` on VM |
| [`db-dev-staging-parity.yml`](../../.github/workflows/db-dev-staging-parity.yml) | Optional ingress; VM verify/migrate |

Full dev↔staging compare runs **on the laptop** with the tunnel.

## Environment variables

| Variable | Example |
|----------|---------|
| `DEV_DATABASE_URL` | `postgresql://postgres@127.0.0.1:5432/Mana_Guruji` |
| `STAGING_DATABASE_URL` | `postgresql://puja_migrate:…@127.0.0.1:15432/Mana_Guruji` |
| `STAGING_SSH` | `opc@140.245.245.201` |
| `STAGING_DB_TUNNEL_PORT` | `15432` |
| `STAGING_DB_PASSWORD` | (optional) builds tunnel URL with `puja_migrate` |

## PM tracker

- **VAL-001** — spec verify on staging (`db-verify`)
- **VAL-002** — dev vs staging deep compare (this doc)
