# TDS readiness script (`check_tds_readiness.py`)

Ops-facing companion to pytest. Run from `puja_platform/` with `.env` `DATABASE_URL` set.

## Usage

```powershell
python scripts/check_tds_readiness.py          # report only (exit 0)
python scripts/check_tds_readiness.py --strict # exit 1 if staging blockers
```

## Sections (v3)

| Section | Meaning |
|---------|---------|
| Migration 025/026 + **028–034** | Schema chain present |
| Pujari PAN / entity_type | Profile readiness counts |
| **v3 exposure (OFF)** | Post-₹5L risk: pujaris over threshold **without operative PAN** (not 5%×all GMV) |
| **Pending recovery** | `SUM(tds_amount)` where `pujari_tds_recovery.status = 'pending'` |
| **TDS reconcile** | Per `(pujari_id, fy_start)`: `tds_accrued` vs ledger net **`accrual+catch_up − reversal`** |
| Turnover vs ledger taxable | Informational drift on crossing bookings (expected v3) |
| Snapshot coverage | §0.L-4 classification at balance collection |
| Accrual intents | Backlog / failed quarantine |

## Staging gate

**Zero TDS drift** under `--strict` is mandatory before `PUJARI_FY_PAN_GATE_ENABLED` (see [`TDS_STAGING_ROLLOUT.md`](./TDS_STAGING_ROLLOUT.md)).

## CA deposit worksheet (read-only)

```powershell
python scripts/export_tds_26q.py --month=2026-04 -o tds_apr.csv
python scripts/export_tds_26q.py --fy=2025 --quarter=4 -o tds_q4_fy2025.csv
```

Uses ledger **`accrual+catch_up − reversal`** for `tds_deducted` and taxable-base net for **`amount_on_which_tds_deducted`**. PAN column blank — supply from KYC out-of-band. See `scripts/README.md`.

Dev DBs polluted by integration tests are **not** staging-ready until FY/ledger rows for test pujaris are quarantined or reset.
