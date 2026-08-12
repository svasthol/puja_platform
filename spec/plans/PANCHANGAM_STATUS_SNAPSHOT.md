# Panchangam — status snapshot

**Last updated:** 2026-08-04  
**Authority:** task rows live in [`STATUS.md`](./STATUS.md); this file is a **handoff dashboard** (not a second source of truth). On conflict, `STATUS.md` wins.

**Maintenance:** update this file in the **same change** as any major panchangam milestone (see [When to update](#when-to-update-this-snapshot) below).

**Ops runbook:** [`PANCHANGAM_OPS.md`](./PANCHANGAM_OPS.md)  
**Normative rules:** `SPEC_AMENDMENTS.md` §23.6, §23.6.1

---

## Integration phases (backend + mobile)

| Phase | Scope | Status | Notes |
|-------|--------|--------|--------|
| **0** | Spec, STATUS, reference CSV, `PANCHANGAM_OPS.md` | **COMPLETED** | §23.6.1 amendments |
| **1** | Engine local (`telugu-panchangam-app` :3001), Venkatrama gate | **COMPLETED** | Lahiri Hyderabad; Jul 2026 reference CSV |
| **2** | Vendor wiring (`panchangam_cities`, beat, cache) | **COMPLETED** | `P-PANCHANGAM-VENDOR` |
| **3** | Accuracy CI + fixtures | **COMPLETED** | `validate_panchangam_accuracy.py` — PASS |
| **4** | Prod deploy (separate node) | **PENDING** | `P-PANCHANGAM-DEPLOY` — EC2/Docker private URL |
| **5** | Customer home ribbon (Flutter) | **IN_PROGRESS** | `C-FLUTTER-PANCHANGAM` — ribbon + device QA vs design 01 |
| **6** | Launch gate + ops sign-off | **PENDING** | `P-PANCHANGAM-LAUNCH-GATE` |

**Not in launch scope:** full calendar tab (`C-PANCHANGAM-CALENDAR`) — **PENDING**, customer app only, post-launch.

---

## Task dashboard

| ID | Status | App / layer |
|----|--------|-------------|
| `P-PANCHANGAM-API` | COMPLETED | Backend — `GET /v1/panchangam` |
| `P-PANCHANGAM-FIELDS` | COMPLETED | Backend — migration 018 columns |
| `P-PANCHANGAM-VENDOR` | COMPLETED | Backend — worker → engine → `panchangam_daily` |
| `P-PANCHANGAM-ACCURACY` | COMPLETED | Backend — reference CSV + CI fixtures |
| `P-PANCHANGAM-DEPLOY` | PENDING | Ops — separate panchangam host |
| `P-PANCHANGAM-LAUNCH-GATE` | PENDING | Ops — checklist in `PANCHANGAM_OPS.md` |
| `C-PANCHANGAM-UI` | **IN_PROGRESS** | **Customer** — home ribbon (`lib/features/customer/`) |
| `C-PANCHANGAM-CALENDAR` | PENDING | **Customer** — full month view (screen 04) |

**Partner app (`P-FLUTTER-PARTNER`):** no panchangam or calendar tasks — not in scope.

---

## Production architecture (target)

```
┌─────────────────────────┐         private VPC          ┌──────────────────────────┐
│  puja_platform host     │  PANCHANGAM_VENDOR_URL       │  panchangam node         │
│  FastAPI :8000          │ ──────────────────────────►  │  telugu-panchangam :3001 │
│  Celery beat → cache      │  (never public)              │  (never mobile-facing)   │
└───────────┬─────────────┘                              └──────────────────────────┘
            │
            │  GET /v1/panchangam only
            ▼
     Customer app (future)
```

Mobile **never** calls the engine. Partner app **never** needs panchangam UI.

---

## Dev port map (same host)

| Service | Port |
|---------|------|
| admin_ui | 3000 |
| telugu-panchangam-app | 3001 |
| puja_platform API | 8000 |

---

## Customer ribbon QA (`C-FLUTTER-PANCHANGAM`)

- Code: `customer_home_screen.dart`, `panchangam_ribbon.dart`.
- **IN_PROGRESS** — device QA vs `managuruji_design.html` screen 01 (`locale=te`/`en`, 404 retry, Drik label) → then **COMPLETED** in `STATUS.md`.

---

## Quick verify commands

```powershell
# Accuracy gate (offline fixtures)
cd puja_platform
python scripts\validate_panchangam_accuracy.py --fixtures spec\fixtures\panchangam_hyderabad_jul2026.json

# Seed one day into cache (engine on :3001)
python scripts\seed_panchangam.py --date 2026-07-15 --locale te

# API smoke
curl "http://127.0.0.1:8000/v1/panchangam?city=Hyderabad&locale=te&date=2026-07-15"
```

---

## What’s next (recommended order)

1. **Partner app** — `P-FLUTTER-FCM-SOUND` + `P-FLUTTER-E2E-SMOKE` (no panchangam dependency).
2. **Pre-launch** — Phase 4 deploy docs (`P-PANCHANGAM-DEPLOY`).
3. **Customer kickoff** — unhold ribbon (`C-PANCHANGAM-UI`).
4. **Post-launch** — full calendar (`C-PANCHANGAM-CALENDAR` + month API).

---

## When to update this snapshot

Update **`PANCHANGAM_STATUS_SNAPSHOT.md`** in the same PR/commit whenever any of these change:

| Trigger | Also update |
|---------|-------------|
| Any `P-PANCHANGAM-*` or `C-PANCHANGAM-*` row flips in `STATUS.md` | Integration phases table + task dashboard + **Last updated** date |
| `C-PANCHANGAM-UI` moves **HOLD** → **COMPLETED** (or back) | HOLD policy section + What's next |
| `P-PANCHANGAM-DEPLOY` completed (prod node live) | Production architecture notes + verify commands if URLs change |
| `P-PANCHANGAM-LAUNCH-GATE` passed or failed | What's next; link checklist outcome in `PANCHANGAM_OPS.md` |
| Accuracy gate fails or reference CSV re-baselined | Phase 1/3 notes; re-run commands in Quick verify |
| New city added to `panchangam_cities.py` | Task dashboard or architecture only if launch scope changes |

**Do not update** for routine partner-app work, minor bugfixes, or dev-only seeds unless a STATUS row changes.

### Update checklist (copy per milestone)

1. Edit the matching row(s) in `STATUS.md` (and `PANCHANGAM_OPS.md` launch checklist if ops-related).
2. Mirror status here: integration phases table, task dashboard, What's next.
3. Set **Last updated** to `YYYY-MM-DD`.
4. If the Panchangam integration dashboard in `STATUS.md` §dashboard exists, ensure it still matches.

**Minor edits** (typos, port map unchanged): snapshot optional. **Major milestones** (table above): snapshot required.
