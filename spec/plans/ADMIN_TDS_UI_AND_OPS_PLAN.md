# Admin console — TDS ops UI & non-blocking performance plan

**Audience:** Engineering, ops, finance  
**Status:** Plan + Phase A implemented (hub, backlog, reconcile UI; FY report query fix)  
**Related:** [`TDS_PRODUCTION_OPS_READINESS.md`](./TDS_PRODUCTION_OPS_READINESS.md) · [`TDS_RUNTIME_CONFIG.md`](./TDS_RUNTIME_CONFIG.md) · [`PAN_FY_GATES.md`](./PAN_FY_GATES.md) · [`TDS_LAUNCH_STATUS.md`](./TDS_LAUNCH_STATUS.md)

---

## 1. Goals

| Goal | Meaning |
|------|---------|
| **Real UI** | Every TDS ops action admins need in staging/prod is reachable in the console with plain-language labels — not only scripts/curl. |
| **No “lag to DB”** | Admin reads are **short, indexed, bounded** (`LIMIT`, filters). No full-table scans on hot partner/customer paths. |
| **Do not block apps** | Partner accept/collect and customer booking flows use **write transactions** on narrow rows. Admin uses **read sessions** (`get_db`) with **no row locks** on bookings; corrections use `get_db_txn` on **one booking** only. |
| **Understandable** | One **TDS hub** groups policy, FY partners, backlog, reconcile, and KYC — same mental model as the month-end runbook. |

---

## 2. Code review summary (current architecture)

### 2.1 Partner / customer hot paths (must stay fast)

| Path | DB pattern | TDS touch |
|------|------------|-----------|
| Accept offer | `get_db_txn` / caller txn; single assignment UPDATE + TDS v3 snapshot | FY gate: 1 pujari row + 1 `SUM(total_amount)` on bookings |
| Confirm balance | booking row UPDATE + Celery accrual intent | FY warn only (non-blocking) |
| TDS accrual worker | Celery on `sweep` queue | Intent row + ledger append; retries on failure |

**Rule:** Admin endpoints must **never** run `SELECT … FOR UPDATE` on `bookings` / `booking_assignments` at scale.

### 2.2 Admin TDS API (already in backend)

| Endpoint | Purpose | Session | Risk if abused |
|----------|---------|---------|----------------|
| `GET /v1/admin/settings/tds-facilitation` | Slab policy | read | Low |
| `GET /v1/admin/pujaris/fy-earnings` | FY collections + gate tier | read + audit commit | **Was N+1** per pujari → fixed to single aggregate query |
| `GET /v1/admin/tds/compliance-backlog` | Parked/failed accrual intents | read, `limit≤200` | Medium — bounded |
| `GET /v1/admin/tds/fy-reconcile` | Accumulator vs ledger drift | read | Medium — only drift rows |
| `POST /v1/admin/tds/bookings/{id}/correct-offline-collection` | Ops correction | **txn**, one booking | Low if rare |

### 2.3 Admin UI (before this plan)

- **Had:** `/console/settings/tds` (slabs), `/console/partners/fy-earnings` (table).
- **Missing:** backlog, reconcile, unified navigation, overview links.
- **Gap vs prod gate:** FY report used `pan_hash IS NOT NULL` for gate display; runtime gate uses **`pan_status = operative`** — aligned in Phase A backend.

### 2.4 Shared DB pool

- API uses one `AsyncEngine` (`DATABASE_POOL_SIZE` default 10, `max_overflow`).
- Admin traffic is **low volume**; risk is **expensive admin reports** starving the pool — mitigated by limits, query fix, and React Query `staleTime` (no hammering refresh).

**Future (optional):** read replica URL for admin-only routes; `statement_timeout` on admin read sessions (e.g. 15s).

---

## 3. Admin information architecture (target)

```
/console/tds                    ← TDS hub (cards + quick counts)
  ├── Policy slabs              → /console/settings/tds
  ├── Partner FY earnings       → /console/partners/fy-earnings
  ├── Accrual backlog           → /console/tds/backlog
  ├── FY ledger reconcile       → /console/tds/reconcile
  └── PAN / KYC                 → /console/partners/kyc
```

**Sidebar:** Primary entry **“TDS hub”** under Settings; keep **“TDS & compliance”** (slabs) and **“Partner FY earnings”** for direct bookmarks.

---

## 4. Performance & safety checklist

### 4.1 Backend

- [x] FY earnings: one SQL round-trip for `SUM(total_amount)` per pujari (gate-aligned gross).
- [x] Gate display: `pan_status = operative` (matches `assert_fy_pan_gate_allowed`).
- [ ] Compliance backlog: ensure index on `(status, created_at)` on `pujari_tds_accrual_intents` if backlog grows (migration when needed).
- [ ] FY reconcile: runs two grouped queries; acceptable at MVP scale; cache or materialized view only if drift checks become slow.
- [ ] Offline correction: ops-only; require `change_reason`; audit via `record_admin_action`.

### 4.2 Admin UI

- [x] Hub + backlog + reconcile pages with `staleTime: 60_000` (1 min) on heavy lists.
- [x] Default `limit=100` on FY earnings (UI); server max 500.
- [ ] Booking-level correction form on booking detail (Phase B) — today API-only.
- [ ] Export buttons → link to `scripts/export_tds_26q.py` / `check_tds_readiness.py` in hub copy (no server-side shell from UI).

### 4.3 What admins must **not** do in UI

- Poll backlog every few seconds (beat + worker drain intents).
- Open FY earnings with `limit=500` in ten tabs during peak hours.
- Use reconcile green/red as substitute for `check_tds_readiness.py --strict` before CA handoff.

---

## 5. Ops runbook (console + scripts)

### 5.1 Daily (2 min)

1. Open **TDS hub** → note backlog counts (parked / pending / failed).
2. If **failed > 0**: open **Accrual backlog** → read `last_error`; fix PAN/entity or data; worker retries.
3. `/health` — `sweep_stale` false (beat alive).

### 5.2 Weekly

1. **Partner FY earnings** — sort by collected gross; filter mentally for **block** tier → chase PAN via **KYC review**.
2. Spot-check 2–3 partners: collected vs facilitation column (should match when accrual on).

### 5.3 Month-end / quarter-end (with CA)

1. `python scripts/check_tds_readiness.py --strict` (authoritative).
2. `python scripts/export_tds_26q.py --month=YYYY-MM`.
3. **FY ledger reconcile** in console — investigate any drift rows before filing.
4. Merge PAN/legal name from KYC (export CSV PAN blank by design).

### 5.4 Dev cleanup (failed intents + ledger already exists)

```bash
python scripts/cleanup_tds_accrual_intents.py          # dry-run
python scripts/cleanup_tds_accrual_intents.py --apply    # mark completed
```

Celery also runs **auto-reconcile** at the start of each `process_tds_accrual_intents` batch.

### 5.5 Incidents

| Symptom | Check | Action |
|---------|-------|--------|
| Partner “PAN required” but FY &lt; ₹5L | `GET /v1/app-config` on **same URL as app** | `PAN_ACCEPT_GATE_ENABLED` vs `PUJARI_FY_PAN_GATE_ENABLED`; OS env override |
| Accept 500 | API logs | e.g. missing imports on gate path (fixed: `Decimal` in `offer_service`) |
| Backlog parked `no_pan` | Backlog UI | Partner Setu operative PAN |
| Reconcile not green | Drift rows | Ops + engineering; do not mass-edit ledger in SQL |

---

## 6. Implementation phases

### Phase A — **Done in repo** (this change set)

- Spec plan (this file).
- Backend: FY earnings single-query gross + operative PAN for gate.
- UI: `/console/tds`, `/console/tds/backlog`, `/console/tds/reconcile`; sidebar + overview links.
- Remove temporary accept-offer debug file logging.

### Phase B — In progress

- [x] **FY reconcile troubleshoot** — `GET /v1/admin/tds/fy-reconcile/troubleshoot?pujari_id=&fy_start=` (bookings + card + ledger; tax vs gross status).
- [x] **Safe fix** — `POST /v1/admin/tds/fy-reconcile/troubleshoot/fix` (re-queue + process accrual for collected bookings missing ledger; max 25; `require_admin_role`; audit).
- [x] Admin UI: **Troubleshoot** per drift row → `/console/tds/reconcile/troubleshoot`.
- [ ] Booking detail: “Correct offline collection” form.
- [ ] Hub: lightweight `GET /admin/tds/summary` (counts only).
- [ ] OpenAPI sync for admin client Zod schemas.

### Phase C — Scale (only if needed)

- Read replica for admin routes.
- `statement_timeout` on admin reads.
- Partial index on accrual intents by status.

---

## 7. Acceptance criteria

- [ ] Ops can complete §5.1–5.3 using **only** console + documented scripts (no undocumented curl).
- [ ] FY earnings page loads in &lt;2s on staging with 200 partners (single DB aggregate query).
- [ ] Accept/collect load test with admin FY page open shows **no** increase in p99 accept latency (manual or k6 spot-check).
- [ ] `pytest tests/test_admin_tds_compliance.py` green after backend changes.

---

## 8. Sign-off

| Role | Date | Notes |
|------|------|-------|
| Engineering | | Phase A merged |
| Ops | | Walkthrough of TDS hub |
| Finance | | Month-end script + reconcile alignment |

---

*Update Phase checkboxes as B/C ship.*
