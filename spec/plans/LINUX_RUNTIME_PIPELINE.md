# Linux runtime pipeline (Windows dev → OL9 staging/prod)

**Goal:** One repeatable path to install **exact** production Python deps on **Linux aarch64** (OCI A1), with CI catching wheel/import issues before SSH deploy.

| Layer | Artifact |
|-------|----------|
| **On VM (S2)** | [`scripts/linux/bootstrap_python_runtime.sh`](../../scripts/linux/bootstrap_python_runtime.sh) |
| **OS RPMs (OL9)** | [`scripts/linux/os-packages.ol9.txt`](../../scripts/linux/os-packages.ol9.txt) |
| **Verify** | [`scripts/verify_linux_runtime.py`](../../scripts/verify_linux_runtime.py) |
| **CI gate** | [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) job `linux-arm64-runtime` |
| **Pins** | [`requirements.txt`](../../requirements.txt) ← from `pyproject.toml` |

---

## Windows vs Linux (no surprises)

| Topic | Windows (dev) | Linux (staging/prod) |
|-------|----------------|----------------------|
| Python | 3.12 venv via **uv** | 3.12 venv via **bootstrap script** or same `pip install -r requirements.txt` |
| Async event loop | **Selector** policy for psycopg async (see `CURSOR_SETUP.md`) | Default asyncio — **no** Windows policy |
| Celery worker | Often `--pool=solo` | **prefork** (default) — no solo in prod |
| `uvloop` / `httptools` | May be omitted on Windows | Installed via `uvicorn[standard]` — **verified on Linux** |
| PostgreSQL / Redis | Local or Docker on laptop | RPM/services on VM (S3) — **not** part of Python bootstrap |
| App code paths | `app/` is OS-agnostic | Same |

**Rule:** If it works in CI job **`linux-arm64-runtime`** and on **`verify_linux_runtime.py`** on `stg-aio-1`, production app nodes (same arch) should match.

---

## Run on `stg-aio-1` (after git clone)

```bash
cd /opt/mana-guruji/src/puja_platform   # or your clone path
chmod +x scripts/linux/bootstrap_python_runtime.sh
./scripts/linux/bootstrap_python_runtime.sh
```

Optional:

```bash
export VENV_DIR=/opt/mana-guruji/venv
export INSTALL_SYSTEM=0   # skip dnf if packages already installed
./scripts/linux/bootstrap_python_runtime.sh
```

---

## Future: staging deploy pipeline

Planned `deploy-staging.yml` will:

1. SSH to `stg-aio-1`
2. `git pull`
3. `./scripts/linux/bootstrap_python_runtime.sh` (idempotent upgrade)
4. Restart systemd units / containers
5. `curl /health`

Same bootstrap script for **production** app nodes after image/git deploy.

---

## Production dependencies (runtime)

From `pyproject.toml` — installed via `requirements.txt`:

FastAPI, uvicorn[standard], orjson, pydantic, SQLAlchemy, Alembic, psycopg[binary,pool], Celery, Redis, PyJWT, bcrypt, cryptography, httpx, boto3, structlog, prometheus-client, python-ulid.

**Not in API venv:** PostGIS (PostgreSQL server extension), Node admin UI, Flutter.

---

## Regenerating `requirements.txt`

After changing `pyproject.toml`:

```bash
uv pip compile pyproject.toml -o requirements.txt
```

Commit `requirements.txt` and let CI re-run.

---

## Tracking

- Staging phase **S2:** [`OCI_INFRA_STATUS.md`](./OCI_INFRA_STATUS.md)
- PM sheet: `project_pm/Mana_Guruji_OCI_PM_Tracker_Staging.csv` row **STG-S2**
