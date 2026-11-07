# Project manager tracker (Excel)

**Purpose:** PM-friendly **staging** and **production** task lists. Open in **Microsoft Excel** or Google Sheets.

| File | Audience |
|------|----------|
| [**`Mana_Guruji_OCI_PM_Tracker_Staging.csv`**](./Mana_Guruji_OCI_PM_Tracker_Staging.csv) | Staging only — `stg-aio-1`, S1–S7, CI, validation, mobile/admin |
| [**`STAGING_PENDING_CHECKLIST.md`**](./STAGING_PENDING_CHECKLIST.md) | Human-readable **pending** backend / frontend / validation |
| [**`Mana_Guruji_OCI_PM_Tracker_Production.csv`**](./Mana_Guruji_OCI_PM_Tracker_Production.csv) | Production only — compartment, 5-node fleet, go-live |
| [`Mana_Guruji_OCI_PM_Tracker.csv`](./Mana_Guruji_OCI_PM_Tracker.csv) | **Index** — points to the two sheets above (not a full task list) |
| [`STG_TO_PROD_PIPELINE.md`](../STG_TO_PROD_PIPELINE.md) | Promotion dev→STG→prod, gates, prod pipelines to build, incident feed-forward |

**Engineering source of truth (keep in sync):**

- OCI progress: [`OCI_INFRA_STATUS.md`](../OCI_INFRA_STATUS.md)
- Code/tasks: [`STATUS.md`](../STATUS.md)
- Prod cut order: [`OCI_PROD_APPLY_SHEET.md`](../OCI_PROD_APPLY_SHEET.md)

---

## How to use in Excel

1. Open **`Mana_Guruji_OCI_PM_Tracker_Staging.csv`** or **`Mana_Guruji_OCI_PM_Tracker_Production.csv`**.
2. **Insert → Table** (header row) for filters.
3. **Status:** `Completed` | `In Progress` | `Not Started` | `Blocked`
4. Set **Completed_Date** = `YYYY-MM-DD` when done.
5. Optional: save as `.xlsx` locally; **commit changes to the `.csv` in git**.

**Production sheet:** first row **STG-GATE** — do not start prod until staging **STG-S6** is **Completed** (update both sheets).

---

## Sync rule

When a task finishes:

1. Update the **staging** or **production** CSV (whichever owns the `Task_ID`).
2. Update [`OCI_INFRA_STATUS.md`](../OCI_INFRA_STATUS.md) and [`STATUS.md`](../STATUS.md) when applicable.
3. If a **Shared** task (e.g. `CI-001`) completes, update **both** CSVs if that row appears in both.

When adding tasks, add to the correct CSV **and** the relevant spec/runbook.

---

## Workstreams

| Value | Typical sheet |
|-------|----------------|
| `Foundation` | Both (shared prerequisites) |
| `Staging-IaC` / `Staging-Configure` | Staging |
| `Production-IaC` / `Production-Configure` | Production |
| `Gate` | Production (staging exit criteria) |
| `CI-CD` / `Mobile-Admin` | Split by `Environment` column |

---

*Last update: 2026-10-24 — STG-CFG-001..003 completed; STG_TO_PROD_PIPELINE.md + incident #21–22*
