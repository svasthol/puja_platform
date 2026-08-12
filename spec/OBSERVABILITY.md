# Observability — architecture and policy (v1)

**Status:** Policy approved (July 2026). **Implementation track:** `spec/plans/OBSERVABILITY.md`.  
**Progress:** `spec/plans/STATUS.md` (Phase 7 dashboard + `M-*` task rows).  
**Behavioural source of truth for booking steps:** `DISPATCH_FLOW.md`.  
**Stuck-state baseline:** `SPEC_AMENDMENTS.md` §10; shipped in Phase 5 as `P-MONITOR` (`app/monitoring/`).

This document is the **normative reference** for metrics, logs, alerts, and per-booking
traceability. It does **not** duplicate task status — see `STATUS.md`.

---

## When this phase runs

**Phase 7 (Observability) starts last** — after:

1. Flutter customer + partner apps (`C-FLUTTER-*`, `P-FLUTTER-*`) reach feature-complete for launch UX
2. Admin control plane exit gate (`ADMIN.md`) is signed off
3. Booking lifecycle APIs are frozen (no pending status renames or new transitions)

Reason: alert rules, dashboards, lifecycle event names, and ops-notification copy all depend on
stable product flows. `M0` (stuck-state foundation) shipped early in Phase 5; the rest of
Phase 7 is intentionally deferred.

---

## Design goals

1. **Vendor-neutral** — any stack that ingests OpenMetrics, JSON logs, or Sentry events
   (Prometheus, Grafana, Loki, Datadog, CloudWatch, VictoriaMetrics, ELK).
2. **Layer-complete** — every integration surface has metrics + logs; critical paths have alerts.
3. **Booking-correlatable** — every lifecycle step loggable/searchable by `booking_id`.
4. **Alert discipline** — engineers paged on **platform broken**; ops notified on **booking needs human action**; no alert fatigue on happy-path volume.
5. **DB remains source of truth** — monitoring supplements `booking_status_history`, `payments`,
   `refunds`, `ops_monitor_alerts`; it does not replace them.

---

## Three signals

| Signal | Purpose | Primary consumers | This repo |
|---|---|---|---|
| **Metrics** | Rates, gauges, histograms, SLIs | Prometheus → Grafana / Datadog | `GET /metrics`, `app/monitoring/metrics.py` |
| **Logs** | Structured events, correlation | Loki / CloudWatch / ELK | structlog JSON (`event` field) |
| **Traces** (optional) | End-to-end latency, causality | Grafana Tempo / Jaeger | Phase 7 `M-OTEL-TRACES` — not started |

---

## Layer taxonomy

Every alert and lifecycle event MUST tag `layer` and `component`:

| `layer` | Scope | Examples |
|---|---|---|
| `api` | FastAPI request handlers | webhooks, checkout, admin mutations |
| `worker` | Celery tasks | dispatch, refund, notifications |
| `sweep` | Beat-driven batch scans | stuck-state monitor, reconfirmation |
| `data` | DB-derived detectors | refund stall scan, KYC backlog gauge |

| `component` | Integration domain |
|---|---|
| `booking` | Lifecycle, dispatch, assignments |
| `payment` | Razorpay orders, webhooks, captures |
| `refund` | Refund worker, failed_permanent queue |
| `dispatch` | Broadcast rounds, exhaustion |
| `webhook` | Inbound payment webhooks |
| `sms` | `sms_router`, OTP, transactional SMS |
| `fcm` | Push notifications |
| `kyc` | Document upload, approval queue |
| `infra` | DB, Redis, Celery broker |

---

## Alert severity matrix (real-world)

| Severity | Who acts | Channel | Examples |
|---|---|---|---|
| **critical** | On-call engineer | PagerDuty / phone | DB down, API 5xx spike, webhook 100% fail |
| **error** | Eng + ops lead | Slack `#incidents` | `refund_failed_permanent`, repeated webhook sig failures |
| **warning** | Ops / RM | Admin in-app + Slack `#ops` | stuck confirmed, dispatch exhausted, refund stall |
| **info** | Ops (dashboard only) | In-app notification, no page | new paid booking, offer accepted |

**Rule:** Do **not** page engineers on every new booking. Use **ops notifications** (`M-BOOKING-NOTIFY`) for attention; use **metrics** for volume dashboards.

---

## Event types (do not rename — downstream rules depend on these)

### `ops_alert` — incident / stuck-state (shipped M0)

Emitted on first occurrence of an open incident. Stored in `ops_monitor_alerts` (migration 016).

| `alert_type` | Severity | Layer | Component |
|---|---|---|---|
| `stuck_payment_pending_webhook_loss` | warning | sweep | payment |
| `stuck_confirmed_no_show` | warning | sweep | booking |
| `refund_stall` | warning | data | refund |
| `refund_failed_permanent` | error | worker | refund |
| `dispatch_exhausted` | warning | worker | dispatch |
| `webhook_signature_invalid` | error | api | webhook |

Log shape (JSON in production):

```json
{
  "event": "ops_alert",
  "alert_type": "stuck_confirmed_no_show",
  "severity": "warning",
  "layer": "sweep",
  "component": "booking",
  "subject_type": "booking",
  "subject_id": "<uuid>",
  "first_seen": true,
  "occurrence_count": 1,
  "description": "...",
  "payload": { }
}
```

Legacy: `booking_no_show_alerts` (migration 015) stays synced for no-show rows.

### `booking_lifecycle` — happy-path + transition audit (planned M1)

One structured log + one Prometheus counter increment per transition:

```json
{
  "event": "booking_lifecycle",
  "booking_id": "<uuid>",
  "step": "payment_captured",
  "from_status": "payment_pending",
  "to_status": "requested",
  "layer": "api",
  "component": "payment",
  "booking_class": "advance"
}
```

Metric: `puja_booking_lifecycle_events_total{step, booking_class, layer}`.

**Canonical `step` values** — must match `DISPATCH_FLOW.md` transitions (implement in order):

| Step | Typical trigger |
|---|---|
| `quote_requested` | `GET /checkout/quote` |
| `hold_created` | `POST /slot-holds` |
| `booking_created` | `POST /bookings` → `payment_pending` |
| `payment_captured` | Razorpay webhook |
| `payment_abandoned` | sweep step 2 |
| `dispatch_enqueued` | webhook / rebroadcast |
| `offer_sent` | dispatch round |
| `offer_expired` | sweep step 3 |
| `offer_rejected` | pujari reject |
| `offer_accepted` | pujari accept |
| `reconfirm_ping_sent` | sweep reconfirmation |
| `reconfirm_escalated` | reconfirmation escalation |
| `rm_dispatch_escalated` | RM escalation scan |
| `service_started` | `POST .../start` |
| `service_completed` | `POST .../complete` |
| `customer_cancelled` | customer cancel |
| `pujari_cancelled` | `POST .../pujari-cancel` |
| `dispatch_exhausted` | `failed_no_pujari` |
| `refund_created` | refund row insert |
| `refund_succeeded` | refund worker |
| `refund_failed_permanent` | refund worker terminal |

DB audit trail (`booking_status_history`) remains authoritative for disputes; lifecycle logs
enable **monitoring-tool timeline** (Loki: `{booking_id="..."}`).

---

## Prometheus metrics (naming convention)

Prefix: `puja_`. Labels: prefer `alert_type`, `layer`, `component`, `step`, `method`, `route`,
`status_class`, `provider`.

### Shipped (M0 — `P-MONITOR`)

| Metric | Type |
|---|---|
| `puja_ops_alert_events_total` | Counter |
| `puja_ops_alert_open` | Gauge |
| `puja_ops_scan_duration_seconds` | Histogram |
| `puja_ops_scan_candidates` | Gauge |
| `puja_webhook_signature_failures_total` | Counter |
| `puja_dispatch_exhausted_total` | Counter |
| `puja_refund_failed_permanent_total` | Counter |
| `puja_http_requests_total` | Counter |
| `puja_http_request_duration_seconds` | Histogram |

Scrape: `GET /metrics` (controlled by `METRICS_ENABLED`).

### Planned (Phase 7)

| Metric | Task |
|---|---|
| `puja_booking_lifecycle_events_total` | `M-LIFECYCLE-EVENTS` |
| `puja_celery_queue_depth` | `M-HEALTH-CELERY` |
| `puja_sms_send_total` / `puja_sms_failures_total` | `M-HEALTH-SMS` |
| `puja_fcm_send_total` / `puja_fcm_failures_total` | `M-HEALTH-FCM` |
| `puja_kyc_pending_gauge` | `M-HEALTH-KYC` |
| `puja_db_pool_in_use` | `M-HEALTH-DB` |
| `puja_redis_ping_seconds` | `M-HEALTH-REDIS` |
| `puja_synthetic_probe_success` | `M-SYNTHETIC-PROBE` |

---

## Ops notifications vs monitoring alerts

| Mechanism | Audience | Storage | Use for |
|---|---|---|---|
| **Ops alert** (`ops_alert`) | Eng + ops | `ops_monitor_alerts` + metrics | Stuck states, security, money risk |
| **Admin notification** | RM / admin staff | `notifications` table | Action required on a booking |
| **Customer/pujari push** | Apps | FCM + `notifications` | Product UX, not ops monitoring |
| **Admin audit** | Compliance | `admin_audit_log` | Who changed what |

Existing admin notification patterns (ship before M2 extends them):

- RM dispatch escalation (`notify_rm_dispatch_escalation`)
- Reconfirm escalation (`notify_reconfirm_escalation`)
- Refund failed (`alert_refund_failed` — log-only today; `M-OPS-NOTIFY-MATRIX` upgrades)

---

## Component health checks

| Component | Liveness (now) | SLI / business health (Phase 7) |
|---|---|---|
| **API** | `/health`, HTTP metrics | Error rate by route, p95 latency |
| **PostgreSQL** | `/health` SELECT 1 | Pool saturation, slow queries |
| **Redis** | `/health` ping | Pub/sub lag, presence key count |
| **Celery** | Worker process up | Queue depth, task failure rate, beat lag |
| **Razorpay** | Webhook sig + stuck payment scan | Capture success rate, webhook latency |
| **Refunds** | stall + failed_permanent alerts | Queue age p95, open count gauge |
| **SMS** | `sms_router` logs | Provider failover rate, DLT rejection counter |
| **FCM** | push retry logs | `fcm_push_exhausted` metric |
| **KYC** | Admin UI queue | Pending docs gauge, approval SLA |
| **Bookings** | stuck-state scanner | Time-in-status histograms, accept rate |

---

## Environment variables

| Variable | Default | Role |
|---|---|---|
| `METRICS_ENABLED` | `true` | Expose `/metrics` |
| `SENTRY_DSN` | empty | Optional error tracking (`pip install .[monitoring]`) |
| `MONITOR_PAYMENT_PENDING_GRACE_MINUTES` | `30` | Added to `BOOKING_PAYMENT_TTL_MINUTES` |
| `MONITOR_CONFIRMED_NO_SHOW_GRACE_MINUTES` | `90` | After scheduled slot (IST) |
| `MONITOR_REFUND_STALL_ATTEMPTS` | `6` | Refund stall threshold |

---

## Grafana / external monitoring integration

1. **Scrape** `http://<api>:8000/metrics` every 15–30s.
2. **Ship logs** — JSON stdout → Loki/Datadog agent (filter `event IN ("ops_alert", "booking_lifecycle")`).
3. **Alert rules** (examples):
   - `puja_ops_alert_open{alert_type="stuck_confirmed_no_show"} > 0` for 5m → `#ops` Slack
   - `rate(puja_http_requests_total{status_class="5xx"}[5m]) > 0.01` → page on-call
   - `puja_synthetic_probe_success == 0` → page on-call
4. **Dashboards** — see `M-GRAFANA-DASHBOARDS` in track file.

---

## Per-booking timeline in a monitoring tool (feasibility)

**Yes.** Recommended approach:

1. **M1** — emit `booking_lifecycle` logs with `booking_id` on every transition.
2. **Log stack** — single-booking timeline via `{booking_id="<uuid>"}`.
3. **Grafana** — link from `ops_alert` panel → Loki explore pre-filtered by `subject_id`.
4. **M-OTEL-TRACES** (optional) — propagate `booking_id` + `request_id` across API → Celery for flame graphs.

`booking_status_history` in PostgreSQL remains the legal/ops audit record; monitoring is for
real-time visibility and incident response.

---

## Related documents

| Document | Role |
|---|---|
| [plans/OBSERVABILITY.md](./plans/OBSERVABILITY.md) | Implementation tasks (`M-*`) |
| [plans/OBSERVABILITY_GAPS.md](./plans/OBSERVABILITY_GAPS.md) | **Living gap register** — update while building Flutter apps |
| [plans/STATUS.md](./plans/STATUS.md) | Task status |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | Stack row (Prometheus + Grafana + Sentry) |
| [DISPATCH_FLOW.md](./DISPATCH_FLOW.md) | Booking lifecycle transitions |
| [DATABASE.md](./DATABASE.md) | `ops_monitor_alerts`, `booking_status_history` |
