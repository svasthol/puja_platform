# Observability track — Phase 7 (post-app-design)

Metrics, logs, ops notifications, dashboards, and synthetic probes. **Runs last** after
Flutter apps + admin UX are feature-complete and booking lifecycle APIs are frozen.

> **Status lives in `STATUS.md` — the single source of truth for implementation progress.**  
> Normative policy: [`spec/OBSERVABILITY.md`](../OBSERVABILITY.md).  
> Track files define scope only: Spec / Files / Acceptance / Depends-on. Never add a
> `Status:` field here; it will drift.

**Prerequisite gate (do not start M1+ until all are true):**

- [ ] `C-FLUTTER-CUSTOMER` + `P-FLUTTER-PARTNER` feature-complete for launch flows
- [ ] `ADMIN.md` exit gate signed off (catalogue, KYC, reassign, refund smoke)
- [ ] No open `DISPATCH_FLOW.md` lifecycle changes in flight
- [ ] Migrations 015 + 016 applied on target environments

---

## Sprint M0 — Stuck-state foundation (shipped Phase 5 as `P-MONITOR`)

Cross-ref only — **do not re-implement**. Status: **COMPLETED** in `STATUS.md`.

| ID | Shipped in | Notes |
|---|---|---|
| `P-MONITOR` | Phase 5 | `app/monitoring/` — registry, emit, scanner, metrics, middleware |
| `P-SWEEP-CONFIRMED` | Phase 5 | Alert-only no-show; syncs `booking_no_show_alerts` |
| `MIG-015` | — | `booking_no_show_alerts` |
| `MIG-016` | — | `ops_monitor_alerts` |

**Verify:** `GET /metrics` exposes `puja_ops_alert_*`; sweep emits `event=ops_alert` on stuck rows.

---

## Sprint M1 — Booking lifecycle instrumentation

Emit one `booking_lifecycle` structured log + `puja_booking_lifecycle_events_total` counter
per transition. Canonical `step` values: `spec/OBSERVABILITY.md` §booking_lifecycle.

### M-LIFECYCLE-EVENTS — Central lifecycle emitter
- **Spec:** `spec/OBSERVABILITY.md` §booking_lifecycle; `DISPATCH_FLOW.md` transitions
- **Priority:** **P0** (blocks per-booking timeline + booking health dashboards)
- **Files:** `app/monitoring/lifecycle.py` (new), wire into:
  - `app/services/booking_service.py`, `webhook_service.py`, `cancellation_service.py`,
    `pujari_cancel_service.py`, `offer_service.py`
  - `app/api/v1/endpoints/service_lifecycle.py`
  - `app/workers/dispatch.py`, `sweep.py`, `refund.py`, `reconfirmation.py`, `rm_escalation.py`
- **Acceptance:**
  - Every row in OBSERVABILITY.md `step` table emits exactly once per transition (idempotent
    re-fires may log at debug only — document per step).
  - Log includes: `booking_id`, `step`, `from_status`, `to_status`, `layer`, `component`,
    `booking_class` when known.
  - Counter `puja_booking_lifecycle_events_total{step,booking_class,layer}` increments.
  - No PII in lifecycle logs (no phone, address, OTP).
- **Depends-on:** Lifecycle API freeze (Phase 7 gate)

### M-LIFECYCLE-WS — WebSocket parity
- **Spec:** `spec/OBSERVABILITY.md`; `API_CONTRACTS.md` §WS
- **Priority:** P1
- **Files:** `app/services/booking_events.py`
- **Acceptance:** Every `booking_lifecycle` step that changes customer/pujari-visible status
  also publishes `status_changed` on `booking:{id}` (or document explicit exceptions).
- **Depends-on:** `M-LIFECYCLE-EVENTS`, `C-WS` / `P-WS`

---

## Sprint M2 — Ops notification matrix (admin / RM attention)

Product notifications for **human action** — distinct from `ops_alert` incidents.
Reuse `app/workers/notifications.py` `_insert_notification` + admin user query pattern.

### M-BOOKING-NOTIFY — New booking attention
- **Spec:** `spec/OBSERVABILITY.md` §Ops notifications; `LAUNCH_POLICY.md` RM mediator
- **Priority:** **P0** (user-requested: admin team sees new bookings)
- **Files:** `app/workers/notifications.py`, call site in `webhook_service.py` (payment captured
  → `requested`) and/or `booking_service.py`
- **Acceptance:**
  - On first transition to `requested` with successful payment: insert `notifications` row
    for all active admin users (`app_context=admin`) + assign RM if `relationship_manager_id` set.
  - Title/body include: puja name, area label, scheduled slot, booking id short ref.
  - **No engineer page** — info severity only.
  - Idempotent: second webhook replay does not duplicate notification.
- **Depends-on:** `M-LIFECYCLE-EVENTS` (or direct hook at webhook), admin users seeded

### M-BOOKING-NOTIFY-CONFIRMED — Confirmed booking attention
- **Spec:** same as above
- **Priority:** P1
- **Files:** `app/services/offer_service.py` (accept path)
- **Acceptance:** On `confirmed`: RM + admin in-app notification (advance bookings: include
  reconfirm reminder in body). Instant bookings: higher-priority copy optional.
- **Depends-on:** `M-BOOKING-NOTIFY`

### M-OPS-NOTIFY-MATRIX — Upgrade weak ops signals
- **Spec:** `spec/OBSERVABILITY.md` §Alert severity matrix
- **Priority:** P1
- **Files:** `app/workers/notifications.py`, `app/monitoring/scanner.py`, `app/workers/refund.py`
- **Acceptance:**
  - `alert_refund_failed` → admin in-app notification (not log-only).
  - `ops_alert` first_seen for `refund_failed_permanent`, `dispatch_exhausted`,
    `stuck_confirmed_no_show` → admin notification (in addition to structured log + metric).
  - Optional Slack webhook env `OPS_SLACK_WEBHOOK_URL` — post on `severity >= error` only.
- **Depends-on:** `M-BOOKING-NOTIFY`, M0 `P-MONITOR`

### M-KYC-NOTIFY — KYC backlog attention
- **Spec:** `spec/OBSERVABILITY.md` §Component health — KYC
- **Priority:** P2
- **Files:** new sweep scan or extend `run_stuck_state_monitor`; `notifications.py`
- **Acceptance:** `pujari_documents` pending > `KYC_BACKLOG_ALERT_THRESHOLD` (default 10) OR
  oldest pending > 48h → weekly admin digest notification (not per-document spam).
- **Depends-on:** `A-KYC` admin queue live

---

## Sprint M3 — Component health metrics

Gauges and counters for dependency SLIs. Each task adds metrics only; alerts wired in M4.

### M-HEALTH-DB — Database pool + query health
- **Spec:** `ARCHITECTURE.md` connection policy; `spec/OBSERVABILITY.md`
- **Files:** `app/db/engine.py`, `app/monitoring/metrics.py`
- **Acceptance:** Export `puja_db_pool_checked_out`, `puja_db_pool_overflow` (or sqlalchemy pool stats);
  `/health` remains liveness-only.
- **Depends-on:** M0

### M-HEALTH-REDIS — Redis latency + connectivity
- **Spec:** `spec/OBSERVABILITY.md`
- **Files:** `app/core/redis_client.py`, `app/monitoring/metrics.py`
- **Acceptance:** Histogram `puja_redis_command_duration_seconds{command}`; gauge from periodic
  ping in sweep or middleware.
- **Depends-on:** M0

### M-HEALTH-CELERY — Queue depth + task outcomes
- **Spec:** `spec/OBSERVABILITY.md`
- **Files:** `app/workers/celery_app.py`, beat hook or sidecar exporter
- **Acceptance:** Gauges `puja_celery_queue_depth{queue}` for `sweep,dispatch,refund,notifications`;
  counter `puja_celery_task_failures_total{task}`.
- **Depends-on:** M0

### M-HEALTH-SMS — SMS provider SLI
- **Spec:** `SPEC_AMENDMENTS.md` §17; `app/services/sms_router.py`
- **Files:** `sms_router.py`, `fast2sms_client.py`, `msg91_client.py`
- **Acceptance:** Counters `puja_sms_send_total{provider,result}`, `puja_sms_failures_total{provider,reason}`;
  alert candidate when failover chain exhausts.
- **Depends-on:** `P-SMS-ROUTER`

### M-HEALTH-FCM — Push delivery SLI
- **Spec:** `DISPATCH_FLOW.md` §Notifications
- **Files:** `app/services/fcm_client.py`, `app/workers/notifications.py`
- **Acceptance:** Counters `puja_fcm_send_total{result}`; increment on `fcm_push_exhausted` path.
- **Depends-on:** `P-NOTIFY`, `P-FCM-E2E` (for live verify)

### M-HEALTH-PAYMENT — Payment pipeline SLI
- **Spec:** `spec/OBSERVABILITY.md`; `DISPATCH_FLOW.md` webhook flow
- **Files:** `webhook_service.py`, `app/monitoring/metrics.py`
- **Acceptance:** Counters `puja_payment_webhook_total{result}`, `puja_payment_capture_total{result}`;
  histogram webhook handler duration. Complements M0 stuck payment alert.
- **Depends-on:** M0, `M-LIFECYCLE-EVENTS`

### M-HEALTH-KYC — KYC queue gauge
- **Spec:** `spec/OBSERVABILITY.md`
- **Files:** `app/monitoring/scanner.py` or dedicated beat task
- **Acceptance:** Gauge `puja_kyc_pending_documents`; labels `verification_status=pending`.
- **Depends-on:** `B-KYC`, `A-KYC`

### M-HEALTH-BOOKING — Time-in-status SLIs
- **Spec:** `spec/OBSERVABILITY.md` §Component health — Bookings
- **Files:** `app/monitoring/scanner.py`
- **Acceptance:** Gauges or histograms: avg time in `requested`, `confirmed`; count by `status`
  (bounded query, not full table scan each tick — use materialized snapshot or sampling).
- **Depends-on:** `M-LIFECYCLE-EVENTS`

---

## Sprint M4 — Dashboards and alert rules

Infrastructure-as-code for Grafana (or Datadog equivalents). **No application code** unless
alert webhook receiver added.

### M-GRAFANA-DASHBOARDS — Ops dashboards
- **Spec:** `spec/OBSERVABILITY.md` §Grafana integration
- **Files:** `deploy/grafana/dashboards/*.json` (new) or `docs/observability/grafana/`
- **Acceptance:** Dashboards for: Platform (HTTP, DB, Redis, Celery), Booking health, Payment,
  Refund, Dispatch, SMS/FCM, Open ops alerts. Each panel links to Loki `booking_id` filter.
- **Depends-on:** M1, M3

### M-GRAFANA-ALERTS — Alert rule bundle
- **Spec:** `spec/OBSERVABILITY.md` §Alert severity matrix
- **Files:** `deploy/grafana/alerts/*.yaml` or provisioning docs
- **Acceptance:** Rules for: `puja_ops_alert_open > 0`, 5xx rate, `puja_synthetic_probe_success == 0`,
  refund stall, Celery queue depth. Routing: critical → PagerDuty; warning → `#ops` Slack.
- **Depends-on:** `M-GRAFANA-DASHBOARDS`

### M-RUNBOOKS — Ops runbook links
- **Spec:** `spec/OBSERVABILITY.md`
- **Files:** `docs/runbooks/*.md` (new)
- **Acceptance:** One runbook per `alert_type` + per component health alert; linked from Grafana
  annotation; steps reference admin UI paths (reassign, refund override, KYC queue).
- **Depends-on:** `M-GRAFANA-ALERTS`

---

## Sprint M5 — Synthetic end-to-end probe

### M-SYNTHETIC-PROBE — Booking pipeline canary
- **Spec:** `spec/OBSERVABILITY.md`; `DISPATCH_FLOW.md` happy path
- **Priority:** **P0** (pre-production go-live gate)
- **Files:** `scripts/synthetic_booking_probe.py` (new), `tests/test_synthetic_probe.py` (unit);
  scheduled via Celery beat or external cron (Grafana Cloud synthetics)
- **Acceptance:**
  - Dev/staging probe: quote → hold → booking → mock webhook → verify `requested` → optional
    accept → `confirmed` (uses test fixtures / seed users).
  - Exposes `puja_synthetic_probe_success` (1/0) + `puja_synthetic_probe_duration_seconds`.
  - Failure emits `ops_alert` with `alert_type=synthetic_probe_failed` (add to registry when implemented).
  - Runs at most once per 15 min; does not pollute production booking data (dedicated test puja/slot).
- **Depends-on:** `M-LIFECYCLE-EVENTS`, clean seed, Celery running
- **Blocked-by (production):** Razorpay test mode or webhook inject path

---

## Sprint M6 — Distributed tracing (optional)

### M-OTEL-TRACES — OpenTelemetry booking traces
- **Spec:** `spec/OBSERVABILITY.md` §Per-booking timeline
- **Priority:** P2 — high value, not go-live blocker
- **Files:** `app/monitoring/tracing.py`, FastAPI + Celery instrumentation
- **Acceptance:** `booking_id` + `request_id` on trace context; spans for API handlers and Celery
  tasks; export to OTLP (Tempo/Jaeger). Sampling: 100% on errors, 1–5% on success in prod.
- **Depends-on:** `M-LIFECYCLE-EVENTS`, observability backend chosen

---

## Phase 7 exit gate

Phase 7 **COMPLETED** when:

- [ ] `M-LIFECYCLE-EVENTS` — all DISPATCH_FLOW transitions instrumented
- [ ] `M-BOOKING-NOTIFY` — admin sees new paid bookings in-app
- [ ] `M-OPS-NOTIFY-MATRIX` — critical ops paths notify admin (not log-only)
- [ ] `M-HEALTH-*` — DB, Redis, Celery, SMS, FCM, Payment, KYC gauges live
- [ ] `M-GRAFANA-DASHBOARDS` + `M-GRAFANA-ALERTS` — deployed to staging
- [ ] `M-SYNTHETIC-PROBE` — green for 7 consecutive days on staging
- [ ] `M-RUNBOOKS` — linked from Grafana
- [ ] `M-OTEL-TRACES` — **SKIPPED** or **COMPLETED** (explicit product call)

---

## Task index (quick reference)

| ID | Sprint | Priority |
|---|---|---|
| M-LIFECYCLE-EVENTS | M1 | P0 |
| M-LIFECYCLE-WS | M1 | P1 |
| M-BOOKING-NOTIFY | M2 | P0 |
| M-BOOKING-NOTIFY-CONFIRMED | M2 | P1 |
| M-OPS-NOTIFY-MATRIX | M2 | P1 |
| M-KYC-NOTIFY | M2 | P2 |
| M-HEALTH-DB | M3 | P1 |
| M-HEALTH-REDIS | M3 | P1 |
| M-HEALTH-CELERY | M3 | P1 |
| M-HEALTH-SMS | M3 | P1 |
| M-HEALTH-FCM | M3 | P1 |
| M-HEALTH-PAYMENT | M3 | P0 |
| M-HEALTH-KYC | M3 | P2 |
| M-HEALTH-BOOKING | M3 | P1 |
| M-GRAFANA-DASHBOARDS | M4 | P1 |
| M-GRAFANA-ALERTS | M4 | P0 |
| M-RUNBOOKS | M4 | P2 |
| M-SYNTHETIC-PROBE | M5 | P0 |
| M-OTEL-TRACES | M6 | P2 |
