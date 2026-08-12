# Panchangam operations runbook

Normative rules: `SPEC_AMENDMENTS.md` §23.6, §23.6.1. Status: `STATUS.md`
(`P-PANCHANGAM-VENDOR`, `P-PANCHANGAM-ACCURACY`, `P-PANCHANGAM-DEPLOY`,
`P-PANCHANGAM-LAUNCH-GATE`). **Dashboard snapshot:** `PANCHANGAM_STATUS_SNAPSHOT.md` — refresh in the same change when any `P-PANCHANGAM-*` / `C-PANCHANGAM-*` STATUS row changes (see snapshot §When to update).

## Reference calendar

- **Edition:** Venkatrama **Chitrapaksha / Lahiri Drik** (check masthead on printed calendar).
- If only Vakya edition available, use manual drikpanchang.com Hyderabad spot-check for Drik
  nakshatra — do not expect string match with Vakya.
- Fill `spec/plans/panchangam_reference_hyderabad.csv` (30 dates) before Phase 2 vendor gate.
- **Audit before gate:** `spec/plans/panchangam_reference_hyderabad_AUDIT.md`

## Accuracy gate (normative)

Of 30 reference dates:

- Every **non-transition** date must match exactly on `tithi.number`, `nakshatra.number`, and `vaaram`.
- At most **2 sunrise-boundary (transition) dates** may mismatch.
- Time fields (rahu, yama, sunrise, sunset): ≥27/30 within tolerance (±3 min rahu/yama; ±2 min sunrise/sunset).

Run: `python scripts/validate_panchangam_accuracy.py` (live engine) or
`python scripts/validate_panchangam_accuracy.py --fixtures spec/fixtures/panchangam_hyderabad_jul2026.json` (CI).

After re-recording fixtures: `python scripts/sync_panchangam_csv_times.py` then re-run gate.

**drikpanchang.com:** manual ops cross-check only — never automate scraping in CI (ToS risk).

## Environment (puja_platform)

**Dev port map (same host):**

| Service | Port | URL |
|---------|------|-----|
| admin_ui (Next.js) | **3000** | http://localhost:3000 |
| telugu-panchangam-app (engine) | **3001** | http://localhost:3001/api/panchangam |
| puja_platform API (FastAPI) | **8000** | http://localhost:8000/v1/panchangam |

```env
PANCHANGAM_VENDOR_URL=http://127.0.0.1:3001/api/panchangam   # dev: panchangam engine (:3001); admin_ui uses :3000
PANCHANGAM_DEFAULT_CITIES=["Hyderabad"]
PLATFORM_TIMEZONE=Asia/Kolkata
# optional:
# PANCHANGAM_API_KEY=
```

**Hyderabad coords:** `lat=17.38500`, `lng=78.48600`, `tz=Asia/Kolkata`.

**Prod:** engine on **separate node** from puja_platform (mana_pujari API host) — private URL only:

```
# On puja_platform host (.env) — NOT exposed to mobile or public internet
PANCHANGAM_VENDOR_URL=http://<panchangam-private-ip>:3001/api/panchangam
```

| Host | Runs | Public? |
|------|------|---------|
| **puja_platform** (mana_pujari) | FastAPI :8000, Celery beat → vendor fetch → `panchangam_daily` | Yes (API) |
| **panchangam node** | `telugu-panchangam-app` :3001 | **No** — VPC/private SG only |

Mobile calls **only** `GET /v1/panchangam` on puja_platform; never the panchangam node.
Phase 4 (`P-PANCHANGAM-DEPLOY`) documents EC2/Docker checklist for the separate node before launch gate.

## Dev engine (telugu-panchangam-app)

**Clone location:** `puja_platform/telugu-panchangam-app` — **not** inside `admin_ui/` (parent
`node_modules` causes EPERM on Windows).

```bash
git clone https://github.com/suhasatluri/telugu-panchangam-app.git
cd telugu-panchangam-app
npm ci
npm run dev   # :3001 (admin_ui owns :3000)
```

**Windows troubleshooting:**

| Issue | Fix |
|-------|-----|
| `EPERM` on `admin_ui/node_modules/@next/swc-*` | Move clone outside `admin_ui/`; stop `admin_ui` dev server |
| Git checkout fails on `*:Zone.Identifier` | Download [main.zip](https://github.com/suhasatluri/telugu-panchangam-app/archive/refs/heads/main.zip) → extract as `telugu-panchangam-app-main/`; optional `Rename-Item telugu-panchangam-app-main telugu-panchangam-app` |
| `sharp` fails (`\|\|` in PowerShell) | `npm config set script-shell C:\\Windows\\System32\\cmd.exe` then `npm ci` |
| All files `deleted` in git status | `git restore --staged .` then `git restore .` |

Verify sample call:

```
GET /api/panchangam?date=YYYY-MM-DD&lat=17.38500&lng=78.48600&tz=Asia/Kolkata&lang=te
```

Pin npm lockfile; no auto-upgrades in prod.

**Fallback:** minimal `panchangam-js` Express adapter if Next.js ops burden grows (document only).

## Launch gate checklist

- [ ] Migrations 017 + 018 applied
- [ ] Venkatrama reference CSV complete (30 dates, Chitrapaksha Drik confirmed)
- [ ] `validate_panchangam_accuracy.py` passes (non-transition exact; ≤2 transition mismatches)
- [ ] Beat populates cache (`fetched_at` in `panchangam_daily`)
- [ ] Flutter ribbon tested `locale=te` and `locale=en`
- [ ] Disclaimer + Drik label visible
- [ ] Booking/dispatch regression: `pytest tests/ -q`
- [ ] Rollback tested (`PANCHANGAM_VENDOR_URL=""` → worker no-op; ribbon 404 retry)

## Rollback

1. Set `PANCHANGAM_VENDOR_URL=""` — worker becomes no-op.
2. Flutter ribbon shows 404 retry (do not crash).
3. Optional: hide ribbon in app config if extended outage.

## Weekly spot-check (post-launch)

- Pick 3 random dates; compare tithi/nakshatra against drikpanchang.com Hyderabad (manual).
- Check beat logs for `fetched=0` streaks (engine down).
- Restart engine if health check fails.

## Non-goals

Panchangam does **not** gate bookings, slot holds, or `is_muhurat_bound` logic.
