# Observability gap register (living document)

**Purpose:** Capture monitoring / metrics / ops-notification gaps **while building** customer and
partner Flutter apps. **Do not implement here** — wire everything in **Phase 7** per
[`OBSERVABILITY.md`](./OBSERVABILITY.md) and [`../OBSERVABILITY.md`](../OBSERVABILITY.md).

**Strategy:** Ship apps first; freeze lifecycle + UX; then execute `M-*` tasks in one pass for
consistent metrics.

**How to use while vibe-coding:**

1. When you ship a Flutter screen or hit a new API path, find its row below.
2. If behaviour differs from the row, **update the row** (same PR or a quick note commit).
3. Add new rows for screens/APIs not listed.
4. Set `Gap noted` = ✅ when you've confirmed the gap in a dev session.
5. Phase 7 implementer checks off `M-*` task when gap is closed.

**Last reviewed:** 2026-07-29 (initial gather — pre-Flutter)

---

## Already shipped (M0 — do not re-build)

| Capability | Where | Phase 7 task |
|---|---|---|
| Stuck `payment_pending` + payment exists | sweep → `ops_alert` | — (done) |
| Stuck `confirmed` no-show (alert-only) | sweep → `ops_alert` + `booking_no_show_alerts` | — (done) |
| Refund stall / `failed_permanent` | scanner + refund worker | `M-OPS-NOTIFY-MATRIX` upgrades notify |
| Dispatch exhausted | dispatch worker | `M-OPS-NOTIFY-MATRIX` |
| Webhook signature invalid | webhooks.py | — (done) |
| HTTP request metrics | `MonitoringMiddleware` | — (done) |
| `/metrics` + `/health` | `main.py` | `M-GRAFANA-*` consumes |
| RM dispatch escalation → admin notify | `notifications.py` | — (done) |
| Reconfirm escalation → admin notify | `notifications.py` | — (done) |

---

## Gap summary (counts)

| Area | Lifecycle log | Ops notify admin | Component metric | WS event | Notes |
|---|---|---|---|---|---|
| Customer Flutter flows | ❌ | ❌ | partial | partial | See §Customer |
| Partner Flutter flows | ❌ | ❌ | partial | partial | See §Partner |
| Backend happy-path | ❌ | ❌ | M0 only | 3 call sites | See §Backend |
| Admin UI | n/a | partial | ❌ | n/a | See §Admin |
| Infra / deps | n/a | n/a | partial | n/a | See §Infra |

---

## Customer app (`C-FLUTTER-CUSTOMER`) — gaps per screen/flow

| Screen / flow | API / event | Lifecycle `step` (planned) | Monitored today? | Phase 7 closes | Gap noted |
|---|---|---|---|---|---|
| Catalog browse | `GET /pujas`, categories | — (no booking yet) | HTTP only | — | ☐ |
| Puja detail | `GET /pujas/{id}` | — | HTTP only | — | ☐ |
| Area + address | `POST/PUT /addresses`, `GET /service-areas` | — | HTTP only | — | ☐ |
| Checkout quote | `GET /checkout/quote` | `quote_requested` | ❌ | `M-LIFECYCLE-EVENTS` | ☐ |
| Slot hold | `POST /slot-holds` | `hold_created` | ❌ | `M-LIFECYCLE-EVENTS` | ☐ |
| Night / instant gate UX | `POST /bookings` 422 | — (error path) | HTTP 4xx only | Log `booking_gate_rejected`? (add in M1) | ☐ |
| Create booking + pay | `POST /bookings`, Razorpay SDK | `booking_created` | ❌ | `M-LIFECYCLE-EVENTS` | ☐ |
| Payment success (webhook) | `POST /webhooks/razorpay` | `payment_captured` | partial WS | `M-LIFECYCLE-EVENTS`, `M-HEALTH-PAYMENT` | ☐ |
| Finding pujari UI | poll `GET /bookings/{id}` | `dispatch_enqueued` | ❌ | `M-LIFECYCLE-EVENTS` | ☐ |
| **New booking → admin attention** | after `requested` | — | ❌ **no admin ping** | **`M-BOOKING-NOTIFY`** | ☐ |
| Booking confirmed | status `confirmed` | `offer_accepted` (server) | partial WS | `M-BOOKING-NOTIFY-CONFIRMED` | ☐ |
| RM block on detail | `GET /bookings/{id}` | — | ❌ | — | ☐ |
| Booking list | `GET /bookings` | — | HTTP only | — | ☐ |
| Customer cancel | `POST .../cancel` | `customer_cancelled` | ❌ | `M-LIFECYCLE-EVENTS` | ☐ |
| WebSocket live status | `WS /bookings/{id}` | — | **3 server publish sites only** | `M-LIFECYCLE-WS` | ☐ |
| Push (FCM) | `POST /me/devices` | — | device row only | `M-HEALTH-FCM`, `P-FCM-E2E` | ☐ |
| OTP login | `POST /auth/otp/*` | — | auth logs | `M-HEALTH-SMS` | ☐ |

**While coding — watch for:**

- [ ] Client retry storms on poll (need rate / error metrics per route?)
- [ ] Razorpay SDK success but webhook delayed → user sees `payment_pending` (M0 alert exists; UX copy?)
- [ ] Duplicate `POST /bookings` idempotency — log `step` once only
- [ ] `booking_class` instant vs advance — tag all lifecycle logs with it

---

## Partner app (`P-FLUTTER-PARTNER`) — gaps per screen/flow

| Screen / flow | API / event | Lifecycle `step` (planned) | Monitored today? | Phase 7 closes | Gap noted |
|---|---|---|---|---|---|
| Register | `POST /pujari/register` | — | ❌ | `M-HEALTH-KYC` funnel | ☐ |
| KYC upload | documents presign | — | ❌ | `M-HEALTH-KYC`, `M-KYC-NOTIFY` | ☐ |
| Availability / unavailability | `PUT /me/availability` | — | HTTP only | — | ☐ |
| Go online | `PUT /me/heartbeat` | — | Redis presence only | `M-HEALTH-REDIS` | ☐ |
| Offers tab (poll) | `GET /offers` | `offer_sent` (server) | ❌ | `M-LIFECYCLE-EVENTS` | ☐ |
| Instant modal / urgency | offer `urgency`, `urgency_escalated` | — | ❌ | lifecycle + FCM metrics | ☐ |
| Accept offer | `POST /offers/{id}/accept` | `offer_accepted` | partial WS | `M-LIFECYCLE-EVENTS` | ☐ |
| Reject offer | `POST /offers/{id}/reject` | `offer_rejected` | ❌ | `M-LIFECYCLE-EVENTS` | ☐ |
| Accept ack push (advance) | FCM `accept_ack` | — | notify logs | `M-HEALTH-FCM` | ☐ |
| Bookings tab | `GET /pujari/bookings` | — | HTTP only | — | ☐ |
| Booking detail | `GET /pujari/bookings/{id}` | — | HTTP only | — | ☐ |
| Start service | `POST .../start` | `service_started` | ❌ | `M-LIFECYCLE-EVENTS` | ☐ |
| Balance collected | `POST .../confirm-balance-collected` | — (add step?) | ❌ | M1 — confirm step name | ☐ |
| Complete | `POST .../complete` | `service_completed` | ❌ | `M-LIFECYCLE-EVENTS` | ☐ |
| Pujari cancel | `POST .../pujari-cancel` | `pujari_cancelled` | partial WS | `M-LIFECYCLE-EVENTS` | ☐ |
| Push (FCM) | `POST /me/devices` | — | device row | `M-HEALTH-FCM` | ☐ |
| 409 on accept (race) | accept contention | — | HTTP 409 only | Dashboard: accept race rate? | ☐ |

**While coding — watch for:**

- [ ] Poll interval 3–5s — document expected `GET /offers` QPS for capacity planning
- [ ] Modal vs inbox UX — log/client analytics for wrong-surface bugs (optional product analytics, not Phase 7)
- [ ] Offline / heartbeat missed → `is_online` drift (presence sync in sweep — analytics only today)
- [ ] Superseded offers disappearing — server trigger OK; client needs graceful empty state

---

## Backend — lifecycle steps not yet emitting `booking_lifecycle`

| Transition | Code location | `step` | WS publish? | Gap noted |
|---|---|---|---|---|
| Quote | `catalog.py` / quote handler | `quote_requested` | — | ☐ |
| Hold | `bookings.py` | `hold_created` | — | ☐ |
| Booking create | `booking_service.py` | `booking_created` | — | ☐ |
| Payment captured | `webhook_service.py` | `payment_captured` | ✅ | ☐ |
| Abandoned payment | `sweep.py` step 2 | `payment_abandoned` | — | ☐ |
| Dispatch round | `dispatch.py` | `offer_sent` | — | ☐ |
| Offer expire | `sweep.py` step 3 | `offer_expired` | — | ☐ |
| Reject | `offer_service.py` | `offer_rejected` | — | ☐ |
| Accept | `offer_service.py` | `offer_accepted` | ✅ | ☐ |
| Reconfirm ping | `reconfirmation.py` | `reconfirm_ping_sent` | — | ☐ |
| Reconfirm escalation | `reconfirmation.py` | `reconfirm_escalated` | — | ☐ |
| RM escalation | `rm_escalation.py` | `rm_dispatch_escalated` | — | ☐ |
| Start / complete | `service_lifecycle.py` | `service_started` / `service_completed` | — | ☐ |
| Customer cancel | `cancellation_service.py` | `customer_cancelled` | — | ☐ |
| Pujari cancel | `pujari_cancel_service.py` | `pujari_cancelled` | ✅ | ☐ |
| Dispatch exhaust | `dispatch.py` | `dispatch_exhausted` | ops_alert ✅ | ☐ |
| Refund * | `refund.py`, cancel paths | `refund_*` | — | ☐ |

---

## Admin (`admin_ui`) — ops visibility gaps

| Ops action | API | Audit (`admin_audit_log`)? | Ops alert / notify? | Gap noted |
|---|---|---|---|---|
| KYC approve/reject | `admin_kyc` | ✅ | ❌ backlog gauge only (M-HEALTH-KYC) | ☐ |
| Manual reassign | `admin_bookings` | ✅ | ❌ on success (only failures logged) | ☐ |
| Refund override | `admin_refunds` | ✅ | ❌ | ☐ |
| Failed refund queue | `GET admin refunds` | read | ❌ proactive alert | ☐ |
| Open ops alerts view | — | ❌ **no UI for `ops_monitor_alerts`** | Phase 7 or admin slice | ☐ |
| Catalogue / pricing | `admin_catalog` | ✅ | — | ☐ |

**Gap:** Admin has no single “ops inbox” merging `notifications` + `ops_monitor_alerts` + stuck
bookings. Consider `A-OPS-INBOX` (future admin task) or Grafana-only for Phase 7.

---

## Infrastructure & dependencies — metric gaps

| Component | Liveness today | SLI metric today | Phase 7 task | Gap noted |
|---|---|---|---|---|
| PostgreSQL | `/health` | ❌ | `M-HEALTH-DB` | ☐ |
| Redis | `/health` | ❌ | `M-HEALTH-REDIS` | ☐ |
| Celery workers + beat | process up (manual) | ❌ | `M-HEALTH-CELERY` | ☐ |
| Razorpay webhooks | sig + stuck scan | partial counters | `M-HEALTH-PAYMENT` | ☐ |
| FAST2SMS / MSG91 | router logs | ❌ | `M-HEALTH-SMS` | ☐ |
| FCM | retry logs | ❌ | `M-HEALTH-FCM` | ☐ |
| S3 KYC / catalog | — | ❌ | optional post-M6 | ☐ |
| End-to-end probe | ❌ | ❌ | **`M-SYNTHETIC-PROBE`** | ☐ |

---

## Alerting & dashboards — not configured until Phase 7

| Item | Status | Task |
|---|---|---|
| Grafana dashboards | ❌ | `M-GRAFANA-DASHBOARDS` |
| Grafana alert rules (PagerDuty / Slack) | ❌ | `M-GRAFANA-ALERTS` |
| Ops runbooks | ❌ | `M-RUNBOOKS` |
| Per-booking Loki timeline | ❌ needs M1 logs | `M-LIFECYCLE-EVENTS` |
| OpenTelemetry traces | ❌ | `M-OTEL-TRACES` (optional) |
| Sentry production DSN | optional env | ship with Phase 7 deploy |

---

## Open questions (resolve during app build — answer in this file)

| # | Question | Owner | Answer |
|---|---|---|---|
| 1 | Should every new **paid** booking notify admin, or only advance / high-value? | Product | _TBD_ |
| 2 | Slack vs email vs in-app only for ops alerts? | Ops | _TBD_ |
| 3 | Client-side analytics (Firebase Analytics) separate from backend Phase 7? | Product | _TBD_ |
| 4 | Synthetic probe: Razorpay test mode vs webhook inject in staging? | Eng | _TBD_ |
| 5 | Admin UI: build `ops_monitor_alerts` inbox or Grafana-only? | Product/Ops | _TBD_ |

---

## Phase 7 entry checklist (run once before starting `M-*`)

Copy to `STATUS.md` Phase 7 gate when ready:

- [ ] `C-FLUTTER-CUSTOMER` — catalog → pay → list → detail → cancel paths QA’d
- [ ] `P-FLUTTER-PARTNER` — register → online → offers → accept → start → complete QA’d
- [ ] `P-FCM-E2E` — at least one real device token push verified
- [ ] `ADMIN.md` exit gate signed off
- [ ] This gap register reviewed — no unknown rows with ☐ unchecked
- [ ] Migrations 015 + 016 applied on staging/prod

---

## Related

- Policy: [`../OBSERVABILITY.md`](../OBSERVABILITY.md)
- Tasks: [`OBSERVABILITY.md`](./OBSERVABILITY.md)
- Status: [`STATUS.md`](./STATUS.md) Phase 7 section
