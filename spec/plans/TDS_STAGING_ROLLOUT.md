# TDS v3 — staging rollout (hard gates)

**Production posture:** platform-bears TDS (platform deposits from its funds; customer pays booking fee only; full puja offline). **`TDS_ACCEPT_STUB_COLLECT=false`** on staging/prod for that model.

**Optional legacy drill:** `TDS_ACCEPT_STUB_COLLECT=true` simulates customer TDS online (shrinks `amount_due_offline`) — do **not** use for platform-bears.

**Live Razorpay TDS capture** (second customer charge) remains blocked until CA **Q-recovery** is signed off. Dormant code: `tds_v3_online_charge.py`.

## Gate 1 — Migration chain (fresh DB)

On a database that **never** saw intermediate 029 patches or conditional 032:

```powershell
cd mana_guruji\puja_platform
python scripts/apply_migrations_028_032.py
```

Expected: idempotent apply of **`028` → `034`** (canonical chain: 029 includes amount-split + refund_reference; 032 intent `cancelled` only; 033 duplicate-safe split; 034 TDS refund reasons).

Verify:

- `bookings.tds_liability_inr`, `tds_collected_online`, `tds_facilitation_fy_applied_at`
- `pujari_tds_facilitation_ledger.refund_reference`
- `ck_bookings_amount_split`: `amount_due_online + amount_due_offline + COALESCE(tds_collected_online,0) = total_amount`
- Re-run script → no errors (no-op)

## Gate 2 — Clean FY + readiness (zero drift)

Historical pytest/dev rows on seed pujari `cccccccc-0000-0000-0000-000000000001` (and peers) **invalidate** reconcile. Before staging flags:

1. **Quarantine or reset** test pollution (dev/staging only — never ad-hoc on production without runbook):

   ```sql
   -- Example: cancel stray accrual intents
   UPDATE pujari_tds_accrual_intents SET status = 'cancelled'
   WHERE status IN ('pending', 'parked', 'failed');

   -- Optional: truncate v3 ledger + FY for a named staging pujari set only
   -- (coordinate with ops — do not truncate production FY)
   ```

2. Run readiness with **strict** reconcile:

   ```powershell
   python scripts/check_tds_readiness.py --strict
   ```

   **Blocker if any:** `tds_accrued != ledger TDS net` per `(pujari_id, fy_start)`, or missing v3 columns.

   FY **turnover** vs ledger taxable net may differ on crossing bookings (informational); **TDS** drift must be **zero**.

## Gate 3 — Staging flags (order)

| Step | Env | Purpose |
|------|-----|---------|
| 1 | `TDS_ACCRUAL_ENABLED=true` | Accept-time FY + liability snapshot; balance ledger materialization |
| 2 | **`TDS_ACCEPT_STUB_COLLECT=false`** | Platform-bears: **`tds_collected_online=0`**, full offline; recovery `pending` = platform owes TDS (deposit from **ledger export**, not recovery sum) |
| 3 | Manual flows | Accept (**operative PAN**, crossing) → collect → refund/reversal drills |
| 4 | `python scripts/check_tds_readiness.py --strict` | Must pass after flows |
| 5 | `PUJARI_FY_PAN_GATE_ENABLED=true` | ₹5L+ **without operative PAN**: block accept / go-online / record-balance |
| 6 | `python scripts/export_tds_26q.py --month=YYYY-MM` | CA worksheet; verify net TDS vs expectations |

**Not in this gate:** live customer TDS Razorpay order (Q-recovery); **`pan_enc`** / automated 26Q upload (Phase 3).

Optional later: `PAN_ACCEPT_GATE_ENABLED` (all accept requires PAN) — supply lever, not day-one staging.

## Gate 4 — Sign-off checklist

- [ ] Gate 1 fresh DB schema match
- [ ] Gate 2 `--strict` green on clean FY
- [ ] Gate 3 flows reconciled (hand-check + readiness)
- [ ] CA Q-recovery documented before stub off

**Related:** [`TDS_V3_IMPLEMENTATION.md`](./TDS_V3_IMPLEMENTATION.md), [`PAN_FY_GATES.md`](./PAN_FY_GATES.md), [`TDS_READINESS.md`](./TDS_READINESS.md).
