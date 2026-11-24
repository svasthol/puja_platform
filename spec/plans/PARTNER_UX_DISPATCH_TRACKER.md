# Partner UX dispatch — implementation tracker

**Closeout base:** `dev` (puja #26 + Flutter #11 merged 2026-11-24)  
**Plan:** `partner_ux_dispatch_fixes_51641824.plan.md`  
**Blindspot review (2026-11-24):** expand notify now targets **inserted** pujari ids only (not full `live` pool).

| Phase | ID | Description | Status |
|-------|-----|-------------|--------|
| 0 | merge-pr22 | PR #22 → `dev` (dispatch worker fixes) | **done** |
| 0+ | ops-celery | Celery worker + beat restart on each deployed env | **pending (ops)** |
| 1–8 | Track B | b1–b11 code + admin UI + Flutter B6 | **done** (puja #23, Flutter #8) |
| A1 | Track A Phase 1 | background `presence_mode` + heartbeat | **done** (puja #24, Flutter #9) |
| C | Track C | quiet-hours advance puja FCM + channels | **done** (puja #25, Flutter #10) |
| C+ | Track C follow-up | daytime silent advance tray + inbox date/net | **done** (puja #26, Flutter #11) |
| 9 | spec/tests | §6 core tests + `DISPATCH_FLOW` + `partner-app.mdc` | **done** |
| 9+ | spec/full | `SPEC_AMENDMENTS`, `LAUNCH_POLICY` prose (optional) | optional |

### §6 tests covered (representative)

| Plan bullet | Test |
|-------------|------|
| B6 modal vs escalation | `test_list_offers_escalated_far_lead_stays_advance_urgency` |
| B9 born-escalated | `test_born_escalated_on_first_ensure_dispatch_windows` |
| B5 flip clamp | `test_effective_flip_clamps_nominal_inside_quiet_to_2130` |
| B11 policy (23:00 / 07:00 vs 14:00) | `test_b11_escalated_delivery.py` |
| Expand past deadline | `test_expand_skips_when_past_deadline` |
| Flip → one expand | `test_flip_task_enqueues_single_expand_per_booking` |
| FCM dedupe (high → normal) | `test_partner_fcm_dedupe.py` |
| Go-online expand gate | `test_heartbeat_go_online.py` |
| Partner net on offers | `test_offers_partner_net.py` |
| Admin validation | `test_admin_rejects_escalation_lead_lte_fail_hours` |
| (+ existing) idempotent flip, live urgency, escalate TTL | `test_urgency_flip.py` |

### Track A

See [`TRACK_A_BACKGROUND_PRESENCE.md`](./TRACK_A_BACKGROUND_PRESENCE.md). Phase 1 merged; **Phase 2 FGS not started**.

### CI/CD on merge to `dev`

See [`DEV_MERGE_STAGING_CI_CHECKLIST.md`](./DEV_MERGE_STAGING_CI_CHECKLIST.md) — `migrate.sh` runs **`apply_migration_040.py`** via G3 manifest; Celery restarted on full deploy.

### Post-merge ops (staging / prod)

1. Deploy API from `dev`; **restart Celery worker + beat**
2. `python scripts/apply_migration_040.py` on any env missing migration 040
3. Ship partner APK from Flutter `dev` (B6 + Track C/C+); fresh install if channels changed
4. Staging smoke: flip, expand, go-online, daytime silent advance tray, quiet puja sound, `partner_net_amount` on `booking_fee` booking
5. Keep **`urgency_escalation_lead_hours` = 4** until partner fleet is on new APK; then raise to **12** in admin

### Remaining (code / CI — not MVP blockers)

| Item | Notes |
|------|--------|
| Track A Phase 2 | Android FGS behind flag; iOS honest UX |
| B11 overnight **integration** | Time-freeze + worker path (policy unit tests exist) |
| `expand_catchup` throttle | 15m Redis cap on `expand_for_pujari` (scale) |
| `offer_advance_batch` | Grouped catch-up FCM (optional product) |
| `FULL_ONLINE_ENABLED` | `payment_splits` + `partner_net` before flag flip |

### Verification

```text
.\.venv\Scripts\python.exe -m pytest tests/test_urgency_flip.py tests/test_quiet_hours.py tests/test_b11_escalated_delivery.py tests/test_admin_dispatch_policy.py tests/test_celery_task_registration.py tests/test_migration_040.py tests/test_partner_ux.py tests/test_phase2_clients.py tests/test_phase2_notifications.py tests/test_partner_fcm_dedupe.py tests/test_offers_partner_net.py tests/test_heartbeat_go_online.py tests/test_launch_slice.py -q
```

**Last updated:** 2026-11-24 (C+ merged — tracker closeout)