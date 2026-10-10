# Mana Guruji — Production ops readiness (TDS + launch companion)

**Audience:** Founder, finance, ops, CA liaison  
**Scope:** Hyderabad MVP with **TDS v3 platform-bears** (`TDS_ACCRUAL_ENABLED=true`)  
**Related:** [`TDS_LAUNCH_STATUS.md`](./TDS_LAUNCH_STATUS.md) · [`TDS_STAGING_ROLLOUT.md`](./TDS_STAGING_ROLLOUT.md) · [`TDS_RUNTIME_CONFIG.md`](./TDS_RUNTIME_CONFIG.md) · [`PAN_FY_GATES.md`](./PAN_FY_GATES.md) · [`ADMIN_TDS_UI_AND_OPS_PLAN.md`](./ADMIN_TDS_UI_AND_OPS_PLAN.md) · [`MVP_GO_NO_GO_CHECKLIST.md`](./MVP_GO_NO_GO_CHECKLIST.md)

---

## 1. Product posture (chosen for production)

| Item | Production choice |
|------|-------------------|
| TDS accrual | **ON** — track FY + TDS in DB; **no** automated deposit to government in app |
| Collection model | **Platform-bears** — customer pays **booking fee** online; **full puja value offline** to pujari |
| PAN policy | **No PAN required to accept until ₹5L FY**; warn ~₹4.5L; **block** at ₹5L without **operative** PAN (Setu verify) |
| Who settles TDS with govt | **Platform** (treasury + CA); **not** withheld from pujari payout in app today (Phase 3) |

### Production `.env` (TDS flags)

```env
TDS_ACCRUAL_ENABLED=true
PAN_ACCEPT_GATE_ENABLED=false
TDS_ACCEPT_STUB_COLLECT=false
PUJARI_FY_PAN_GATE_ENABLED=true
PUJARI_TAX_PROFILE_REQUIRED_FOR_ACCEPT=false
```

Also required: `APP_ENV=production`, `DEBUG=false`, Setu **production** `KYC_SETU_*` + **`KYC_SETU_PAN_PRODUCT_ID`**, Razorpay live keys only if taking live payments.

**Verify after deploy:** `GET /v1/app-config` on the **production URL** must show `pan_accept_gate_enabled: false`, `pujari_fy_pan_gate_enabled: true`, `tds_accrual_enabled: true`.  
**Note:** OS-level env vars override `.env` on Windows/Linux — if app-config disagrees with the file, check process environment.

Restart **uvicorn** and **Celery** after any `.env` change.

---

## 2. Pre-launch gates

### 2.1 Legal / CA / owner

| # | Task | Owner | Done |
|---|------|-------|------|
| L5 | **§0.C risk acceptance** signed (v3 exposure: post-₹5L slice; not “5% × all GMV”) with real **G** / crossing share | Founder/finance | ☐ |
| L6 | PAN-drive owner, TAN owner, CA memo sender named; memo sent | Ops | ☐ |
| — | **Q-recovery** (how platform funds TDS deposit) documented; CA sign-off | CA + founder | ☐ |
| — | **TAN** application started (long lead; Phase 3 deposit) | Finance | ☐ |

### 2.2 Staging sign-off (S14) before production accrual ON

| # | Task | Done |
|---|------|------|
| — | Migrations **028→034** on production DB per runbook (`scripts/apply_migrations_028_032.py` / deploy process) | ☐ |
| — | E2E: accept below ₹5L without PAN → collect balance → complete | ☐ |
| — | Crossing ₹5L: block without operative PAN; accept after Setu **operative** PAN | ☐ |
| — | Cancel/refund reversal drills (T7) | ☐ |
| — | `python scripts/check_tds_readiness.py --strict` **green** (zero TDS ledger vs `tds_accrued` drift) | ☐ |
| — | Spot-check `python scripts/export_tds_26q.py --month=YYYY-MM` | ☐ |
| — | Mobile + Phase 0b API **same release** (FY gate codes, tax summary, PAN UX) | ☐ |
| — | Device QA: warn banner, block dialog, confirm-balance warn (`FY_PAN_GATE_WARN`) | ☐ |

### 2.3 MVP go/no-go (non-TDS)

Complete [`MVP_GO_NO_GO_CHECKLIST.md`](./MVP_GO_NO_GO_CHECKLIST.md): API without dev reload, TLS/LB, backups, DLT/SMS if live OTP, admin bootstrap, etc.

---

## 3. Infrastructure (production)

| Component | Requirement |
|-----------|-------------|
| **API** | `uvicorn` / gunicorn behind LB; bind `0.0.0.0`; **not** `--reload` |
| **Celery worker** | `-Q sweep,dispatch,refund,notifications`; TDS accrual tasks on `sweep` |
| **Celery beat** | **Single instance globally** (30s sweep, accrual beat hook) |
| **Redis** | Broker + cache |
| **Postgres** | Migrations applied; PostGIS; pool budget vs API + workers |
| **Secrets** | Vault / `.env` on host only; never in git |
| **Health** | `/health` for LB; `/health/live` for reachability |
| **Observability** | Structured logs; Sentry if configured; `sweep_stale` false (beat alive) |

---

## 4. Support playbook (partner behaviour)

| Situation | Expected behaviour |
|-----------|-------------------|
| Pujari, FY &lt; ₹5L, no PAN | Can **go online** and **accept** (subject to KYC verified, dispatch, etc.) |
| FY ~₹4.5L–₹5L | **Warning** — add/verify PAN (tax summary + app copy) |
| Accept would push FY ≥ ₹5L, no **operative** PAN | **422** `FY_PAN_GATE_BLOCKED` — “PAN required” in app |
| PAN on file but not Setu-verified | Not **operative** — still blocked at ₹5L tier |
| After **operative** PAN, slice above ₹5L | **0.1%** TDS **accrued** on taxable slice (individual/HUF); puja cash offline unchanged |
| Firm/company (“always taxed” entities) | Often **0.1%** from first rupee — not individual ₹5L exemption |

**FY gross for gate:** sum of `bookings.total_amount` with `balance_collected_at` in Indian FY; **accept** adds this booking’s `total_amount` for **projected** crossing check.

---

## 5. Month-end / quarter-end (recurring ops)

| Step | Action |
|------|--------|
| 1 | `python scripts/check_tds_readiness.py` (use `--strict` per runbook on prod) |
| 2 | `python scripts/export_tds_26q.py --month=YYYY-MM` or `--fy=YYYY --quarter=N` |
| 3 | Merge export with **operative PAN + legal name** from admin/KYC (export CSV leaves PAN blank — see `scripts/README.md`) |
| 4 | Send package to **CA** for deposit amount + **26Q** filing |
| 5 | **Treasury** pays government per CA (confirm due dates, e.g. 7th of following month) |
| 6 | Monitor: count of pujaris over ₹5L **without operative PAN** (target ~0); pending **recovery** rows |

**Not automated in app:** government payment, TRACES upload, Form 16A to pujaris (Phase 3 `P-TDS-393`).

---

## 6. Launch day checklist

- [ ] Prod `.env` TDS block per §1; `GET /v1/app-config` verified on prod URL
- [ ] Celery worker + beat running; `/health` not `sweep_stale`
- [ ] Setu PAN verify live (`setu_pan_verify_configured: true`)
- [ ] Partner + customer apps use **production API** base URL
- [ ] Admin: roles, RM, catalogue; TDS hub reviewed (`/console/tds` — slabs, FY earnings, backlog, reconcile)
- [ ] On-call: OTP/DLT, Razorpay, FY PAN block escalation, export scripts path
- [ ] Rollback discussed: `TDS_ACCRUAL_ENABLED=false` stops new accrual posture (does not erase historical ledger)

---

## 7. Out of scope for this launch

- Phase 3: payout withhold, automated deposit, `pan_enc` filing automation, live second Razorpay TDS charge (Q-recovery)
- Flutter earnings / “TDS deducted from bank” UI
- Removing **5% fail-safe** from accrual math (still applies if over ₹5L without operative PAN when gate bypassed — rely on FY gate + PAN drive)

---

## 8. Sign-off

| Role | Name | Date | Notes |
|------|------|------|-------|
| Engineering (S14) | | | Staging strict + export spot-check |
| Product | | | Device QA FY/PAN flows |
| Finance / CA | | | §0.C + month-end process |
| Founder | | | Accrual ON in prod approved |

---

*Created for ops handoff; update checkboxes and names before production flip.*
