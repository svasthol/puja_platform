# Partner UX dispatch — implementation tracker

**Branch:** `feature/urgency-flip-rebroadcast`  
**Plan:** `partner_ux_dispatch_fixes_51641824.plan.md`  
**Blindspot review (2026-11-24):** expand notify now targets **inserted** pujari ids only (not full `live` pool).

| Phase | ID | Description | Status |
|-------|-----|-------------|--------|
| 0 | merge-pr22 | PR #22 → `dev`; Celery worker + beat restart | **pending (ops)** |
| 1–8 | Track B | b1–b11 code + admin UI + Flutter B6 | **done** (puja #23, Flutter #8) |
| A1 | Track A Phase 1 | background `presence_mode` + heartbeat | **done** (puja #24, Flutter #9) |
| C | Track C | quiet-hours advance Om FCM + inbox badge | **in PR** `feature/track-c-advance-om-quiet` |
| 9 | spec/tests | §6 core tests + `DISPATCH_FLOW` + `partner-app.mdc` | **done** |
| 9+ | spec/full | `SPEC_AMENDMENTS`, `LAUNCH_POLICY` prose (optional) | optional |

### §6 tests covered (representative)

| Plan bullet | Test |
|-------------|------|
| B6 modal vs escalation | `test_list_offers_escalated_far_lead_stays_advance_urgency` |
| B9 born-escalated | `test_born_escalated_on_first_ensure_dispatch_windows` |
| B5 flip clamp | `test_effective_flip_clamps_nominal_inside_quiet_to_2130` |
| Expand past deadline | `test_expand_skips_when_past_deadline` |
| Flip → one expand | `test_flip_task_enqueues_single_expand_per_booking` |
| Admin validation | `test_admin_rejects_escalation_lead_lte_fail_hours` |
| (+ existing) idempotent flip, live urgency, escalate TTL | `test_urgency_flip.py` |

### Track A

See [`TRACK_A_BACKGROUND_PRESENCE.md`](./TRACK_A_BACKGROUND_PRESENCE.md). Phase 1 merged; Phase 2 FGS not started.

### CI/CD on merge to `dev`

See [`DEV_MERGE_STAGING_CI_CHECKLIST.md`](./DEV_MERGE_STAGING_CI_CHECKLIST.md) — `migrate.sh` runs **`apply_migration_040.py`** via G3 manifest; Celery restarted on full deploy.

### Not in scope for Track B closeout

- Full overnight B11 matrix (23:00/14:00, 07:00 urgent) — add when time-freeze CI helper exists
- Heartbeat → `expand_for_pujari` integration test (needs Redis + post_commit harness)
- Track A Phase 2 FGS
- `offer_advance_batch` grouped FCM

### Before Track A

1. Merge PR #22, rebase feature branch on `dev`
2. `python scripts/apply_migration_040.py` on target envs
3. Open Track B PR; ship partner build with B6
4. Staging smoke (flip, expand, go-online)

### Verification

```text
.\.venv\Scripts\python.exe -m pytest tests/test_urgency_flip.py tests/test_quiet_hours.py tests/test_admin_dispatch_policy.py tests/test_celery_task_registration.py tests/test_migration_040.py -q
```

**Last updated:** 2026-11-24