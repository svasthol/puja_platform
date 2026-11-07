# E2E log capture (Slice B / pre–Slice C)

All runtime log files in this folder are **gitignored** (`*.log`). Only this README and `.gitkeep` are tracked.

## File names (convention)

| File | Service |
|------|---------|
| `api.log` | FastAPI / uvicorn |
| `adminui.log` | Next.js admin (`admin_ui/`) |
| `customer.log` | Flutter customer (`mana_guruji_mobile/`) |
| `partner.log` | Flutter partner |
| `celery-workers.log` | Celery worker |
| `beat.log` | Celery beat |
| `e2e-ui.log` | `python tests/e2e_ui/serve.py` (E2E static UI + proxy) |
| `redis.log` | Optional: `redis-cli MONITOR` (dev only — very noisy) |

Paths are always under **`puja_platform/logs/`** from the repo root `puja_platform/`.

## Log rotation (dev)

PowerShell **`Tee-Object -Append`** keeps growing the same file until you **rotate** or **truncate**.

- **Before starting work**, move active logs aside:

```powershell
cd puja_platform
pwsh -File scripts/rotate_dev_logs.ps1
```

This moves `logs/*.log` → `logs/archive/<name>-yyyyMMdd-HHmmss.log` (gitignored). Next `Tee-Object` run creates a **new** empty file.

- **Manual:** delete or rename `logs/api.log` etc.

There is **no built-in size rotation** in these helpers; for long-running processes, run `rotate_dev_logs.ps1` daily or when files get large (e.g. > 50 MB).

## Windows (PowerShell) — tee stdout/stderr into files

From `puja_platform/` with venv active and env loaded:

```powershell
New-Item -ItemType Directory -Force logs | Out-Null

# API — match your usual one-liner (Windows event loop + reload)
python -c "import asyncio; asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy()); import uvicorn; uvicorn.run('app.main:app', host='0.0.0.0', port=8000, reload=True)" *>&1 | Tee-Object -FilePath logs/api.log -Append

# E2E UI server (from puja_platform/)
python tests/e2e_ui/serve.py *>&1 | Tee-Object -FilePath logs/e2e-ui.log -Append

# Celery (your exact queues / pool — run each in its own terminal)
celery -A app.workers.celery_app worker --loglevel=info -Q sweep,dispatch,refund,notifications --pool=solo *>&1 | Tee-Object -FilePath logs/celery-workers.log -Append
celery -A app.workers.celery_app beat --loglevel=info *>&1 | Tee-Object -FilePath logs/beat.log -Append
```

From `puja_platform/admin_ui/` (use **`npm.ps1`** if that is how you invoke npm on your machine):

```powershell
# npm.ps1 run dev *>&1 | Tee-Object -FilePath ../logs/adminui.log -Append
npm run dev *>&1 | Tee-Object -FilePath ../logs/adminui.log -Append
```

From **`mana_guruji/mana_guruji_mobile/`** (sibling of `puja_platform/`):

```powershell
flutter run --flavor customer -t lib/main_customer.dart --dart-define=API_BASE_URL=http://127.0.0.1:8000 -v *>&1 | Tee-Object -FilePath ../puja_platform/logs/customer.log -Append
flutter run --flavor partner   -t lib/main_partner.dart   --dart-define=API_BASE_URL=http://127.0.0.1:8000 -v *>&1 | Tee-Object -FilePath ../puja_platform/logs/partner.log -Append
```

Emulator API host is often `http://10.0.2.2:8000` (Android); keep the same `Tee-Object` path.

## Redis (optional, dev only)

**`MONITOR` echoes every command — high volume.** Use a short window or dedicated Redis for dev.

```powershell
redis-cli -u $env:REDIS_URL MONITOR *>&1 | Tee-Object -FilePath logs/redis.log -Append
```

If `REDIS_URL` is not a `redis-cli` URL, pass `-h host -p port` explicitly.

## Helpers

- **`scripts/start_dev_with_logs.ps1`** — opens **minimized** `pwsh` windows for API, worker, beat, E2E UI, admin, **customer + partner** Flutter (if `../mana_guruji_mobile` exists). Example: `pwsh -File scripts/start_dev_with_logs.ps1 -RotateFirst`
  - **Preflight (default):** skips start with a **yellow `[SKIP] … already running`** if something listens on API **8000**, admin **3000**, E2E **8765**, or if a **Celery** process for `app.workers.celery_app` with `worker` / `beat` is already running. Use **`-Force`** to start anyway (second instance), or **`-SkipPreflight`** to disable checks.
  - **Ports:** `-ApiPort`, `-AdminPort`, `-E2EPort` if you use non-defaults (must match `next dev` / `serve.py`).
  - **Flutter:** duplicate runs are **not** auto-detected; use `-SkipFlutterCustomer` / `-SkipFlutterPartner` or close the existing `flutter run` first.
- **`scripts/rotate_dev_logs.ps1`** — move active `logs/*.log` into `logs/archive/` with a timestamp before a new dev session.
- **`scripts/e2e_log_capture.ps1`** — creates `logs/`, prints commands for copy-paste.
- **`scripts/watch_e2e_logs.ps1`** — every N minutes, scans `logs/*.log` for `ERROR`, `Traceback`, `Exception`, HTTP **`4xx`** and **`5xx`** (standalone status codes in log lines), `DioException`, Redis hints (for humans or for a Cursor Task to run periodically). Many `200`/`304` lines will not match; tune patterns in the script if a log format is too noisy.

### Production-style rotation

On a real host, prefer **systemd journal**, **Docker logging**, or a **log shipper** with max size — not `Tee-Object`. What we document here is for **local dev / manual QA**.

## Cursor Task subagent

Use a **recurring Task** (interval N minutes) that:

1. Runs `pwsh -File scripts/watch_e2e_logs.ps1 -IntervalMinutes 0 -Once` (one-shot scan), **or**
2. Reads the tail of each `logs/*.log` and summarizes anomalies.

The agent cannot see your terminals unless logs are **written to these files** (or pasted).
