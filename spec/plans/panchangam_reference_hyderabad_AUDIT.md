# Panchangam reference CSV — audit (Aug 2026)

**File audited:** `panchangam_reference_hyderabad.csv`  
**Sources used:** `@ishubhamx/panchangam-js@2.2.6` (Lahiri, Hyderabad `17.385/78.486`, `timezoneOffset=330`), drikpanchang.com spot-checks, internal consistency.

**Verdict:** Rows **Jul 14–20** and **Jul 30** corrected (Aug 2026) per `panchangam-js@2.2.6` Lahiri Udaya values. **Jul 16–17** also fixed (cascade from Jul 15). Remaining rows still Drikpanchang-sourced — spot-check against Venkatrama book before Phase 1 gate.

## How to read tithi numbers (engine)

`panchangam-js` uses `tithi` 0–29 at sunrise (Udaya):

| Number | Tithi |
|--------|-------|
| 0 | Shukla Pratipada (పాడ్యమి) |
| 1–13 | Shukla Dwitiya … Chaturdashi |
| 14 | Purnima |
| 15 | Krishna Pratipada |
| 16–28 | Krishna Dwitiya … Chaturdashi |
| 29 | Amavasya |

## Confirmed mismatches (CSV vs engine vs drikpanchang)

| Date | CSV tithi | Engine `tithi#` | Expected (Udaya) | Issue |
|------|-----------|-----------------|------------------|-------|
| 2026-07-14 | Chaturdashi | 29 | **Amavasya** | Wrong — Amavasya day |
| 2026-07-15 | Amavasya | 0 | **Shukla Pratipada** | Wrong — new Shukla month starts |
| 2026-07-18 | Tritiya | 4 | **Panchami** | Off by 2 |
| 2026-07-19 | Saptami | 5 | **Shashthi** | Wrong (note already flagged Shashthi) |
| 2026-07-20 | Panchami | 6 | **Saptami** | Wrong — sequence break |
| 2026-07-23 | Ashtami | 8 | Ashtami | OK |
| 2026-07-30 | Purnima | 15 | **Krishna Pratipada** | Wrong — not Purnima |

**drikpanchang spot-check (Jul 15, 2026):** Shukla Pratipada, Pushya nakshatra, Wednesday — matches **engine**, not CSV (CSV had Amavasya / Punarvasu).

**drikpanchang spot-check (Jul 19, 2026):** Shashthi (until ~03:29 next day), Uttara Phalguni — matches **engine** Shashthi, not CSV Saptami.

## Likely transition days (mark for ≤2 exemption gate)

| Date | Reason |
|------|--------|
| 2026-07-02 | Note: Dwitiya ends near sunrise |
| 2026-07-14 | Amavasya boundary |
| 2026-07-15 | Shukla Pratipada begins at sunrise |
| 2026-07-19 | Shashthi → Saptami near sunrise (Jul 20) |

## Rows that look OK (spot-checked)

| Date | vaaram | tithi | nakshatra |
|------|--------|-------|-----------|
| 2026-07-01 | Wed | Krishna Pratipada (పాడ్యమి) | Purva Ashadha — matches engine `tithi#15`, `nak#19` |
| 2026-07-06 | Mon | Shashthi | engine `tithi#20` |
| 2026-07-16 | Thu | Shukla Pratipada | engine `tithi#1` |

## What to do next

1. **Re-fill CSV from Venkatrama book** (preferred) — one row per day, Udaya values at Hyderabad sunrise.
2. **Manual drikpanchang** — set city to Hyderabad in browser UI; transcribe by hand (do not scrape).
3. Add columns `tithi_number`, `nakshatra_number` for script comparison (optional).
4. Re-run Phase 1 only after CSV corrected.

## npm / clone issue (Windows)

- Clone inside `admin_ui/` can conflict with parent `node_modules` (EPERM on `@next/swc-win32-x64-msvc`).
- Git checkout may fail on `*:Zone.Identifier` files — use zip download or WSL clone.
- Run `npm ci` via **cmd.exe** (not PowerShell) if `sharp` postinstall fails on `||`.
- Recommended path: `puja_platform/telugu-panchangam-app` (sibling of `admin_ui`, not inside it).
