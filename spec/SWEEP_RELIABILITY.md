# Sweep reliability & dispatch deadline enforcement

**Status:** SHIPPED (2026-08-30)  
**Migration:** `024` (`worker_heartbeats`)  
**Task:** P-SWEEP-RELIABILITY — **COMPLETED** (`spec/plans/STATUS.md`)

## Incident summary

Bookings stayed in `requested` for hours after `dispatch_deadline` passed because **Celery beat was not running** (Redis outage killed the scheduler). The exhaust SQL was correct; it simply never executed. Four bookings were affected in dev.

## Root causes (verified)

| Issue | Impact | Fix |
|-------|--------|-----|
| Beat not supervised | Silent scheduler death | Ops: supervise beat (`Restart=always`); monitor `/health` `sweep_stale` |
| No sweep heartbeat | No alert when sweep stops | Postgres `worker_heartbeats` + `/health` `sweep_age_seconds` |
| `sweep_lock` un-namespaced, no owner token, TTL 25s | Cross-env lock collision; stolen lock | `APP_ENV:` prefix, owner-token release, TTL 90s |
| Raw Redis client in sweep (no timeouts) | Half-open socket wedges solo worker | `app/workers/redis_sync.py` shared client |
| Reconfirmation/monitor exceptions block exhaust | One step failure skips deadline enforcement | Per-step `_safe_step` isolation in `run_sweep` |
| Exhaust loop unbounded, no per-booking try/except | One bad row blocks batch | `LIMIT 50` + per-booking try/except |
| NULL `dispatch_deadline` treated as in-window for rebroadcast | Permanent rebroadcast trap | Require non-NULL deadline + future slot for rebroadcast |
| `max_rounds` column never enforced | Rounds exceeded cap (6 rows in dev) | Enforce in `_dispatch_round` + rebroadcast scan |
| No past-slot gate at booking creation | Past slots bookable | `SLOT_IN_PAST` 422 in `assert_booking_gate` |
| Eligibility missing slot-in-future | Offers for past pujas | `(scheduled_date + scheduled_time) > now()` in `_eligibility_predicates` |
| Accept without slot check | Past slot confirmable | `assert_slot_not_past_for_accept` → 410 |

## Operational requirements

1. **Always run beat and worker together:**
   ```bash
   celery -A app.workers.celery_app beat --loglevel=info
   celery -A app.workers.celery_app worker --loglevel=info -Q sweep,dispatch,refund,notifications --pool=solo
   ```
2. **Apply migration 024:** `python scripts/apply_migration_024.py`
3. **Monitor `/health`:** `sweep_stale: true` or `sweep_age_seconds > 120` → page ops (beat dead or sweep failing).
4. **Redis:** use stable endpoint (Elastic IP / DNS); prod requires `requirepass` + TLS.

## Code map

| File | Role |
|------|------|
| `app/workers/sweep.py` | Exhaust batch, isolated steps, `sweep_done` log |
| `app/workers/sweep_heartbeat.py` | Postgres heartbeat read/write |
| `app/workers/redis_sync.py` | Sync Redis client + owner-token locks |
| `app/workers/dispatch.py` | `max_rounds` cap before next round |
| `app/services/booking_gate.py` | `SLOT_IN_PAST` gate |
| `app/services/slot_guard.py` | Accept-time slot guard |
| `app/services/dispatch_launch.py` | Eligibility slot-in-future |
| `app/main.py` | `/health` sweep_age + sweep_stale |
| `tests/test_sweep_reliability.py` | Regression tests |

## Exhaust predicate (canonical)

```sql
-- failed_no_pujari when deadline passed OR (NULL deadline AND slot passed)
WHERE status = 'requested' AND pujari_id IS NULL AND cancelled_at IS NULL
  AND (
    (dispatch_deadline IS NOT NULL AND dispatch_deadline <= now())
    OR (dispatch_deadline IS NULL AND (scheduled_date + scheduled_time) <= now())
  )
```
