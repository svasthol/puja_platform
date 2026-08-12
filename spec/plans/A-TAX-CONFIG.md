# A-TAX-CONFIG — admin tax configuration (commercial only)

**Normative companion:** `GST_Withholding_Tax_Model_v1.2.pdf` (§5–§8) · **Index:** SPEC_AMENDMENTS.md §16  
**Supersedes:** `A-COMMISSION` (`platform_settings` commission/gst — never implement)  
**DDL:** `spec/db/migration_007.sql` — **tables may be created without CA memo**  
**Statutory seed:** requires CA memo → `advisor_signoff_ref` on first `tax_statutory_config` row  
**Status:** Phase 3 **ON HOLD** for checkout snapshot + splits; Phase 4 may ship **read-only** tax UI after mig 007 DDL

## Policy

> **If an ops person can change it without a CA memo, it must be a *price* — never a statutory *rate*.**

| Class | Mechanism |
|---|---|
| **Commercial** (`platform_fee_gross`, `platform_fee_inclusive`, `commission_pct`) | `tax_commercial_config` — Admin API, INSERT-only grant |
| **Statutory + legal** (GST%, TDS%, `puja_gst_treatment`, etc.) | `tax_statutory_config` — **`puja_migrate` only**; `REVOKE INSERT FROM puja_app` |

**Temporal:** latest-wins `effective_from DATE UNIQUE` — append-only, no UPDATE to close rows.

**Snapshot:** `tax_*_config_id` + fee on **`slot_holds`** at quote; booking inherits — never re-reads current.

## Migration 007 — DDL vs seed (no contradiction)

| Step | CA memo required? | Who |
|---|---|---|
| `CREATE TABLE tax_statutory_config`, `tax_commercial_config`, snapshot columns on hold/booking | **No** | migration 007 via Alembic |
| `INSERT` statutory rates + `advisor_signoff_ref` | **Yes** | `puja_migrate` role only |
| `POST /v1/admin/tax-config/commercial` | **Yes** (needs seeded statutory row for preview) | Admin API after Phase 3 unhold |
| Checkout quote/hold snapshot (`C-QUOTE`, `C-HOLD`, `C-BOOK`) | **Yes** | Phase 3 — not while ON HOLD |

## Admin API

- `GET /v1/admin/tax-config/current` — commercial + statutory (read-only) + CGST/SGST/IGST preview
- `GET /v1/admin/tax-config/history` — cursor paginated audit
- `POST /v1/admin/tax-config/commercial` — **only** price fields + `effective_from` + `change_reason`
- Statutory keys in body → **422** (never silently ignored)

Phase 4: implement **GET** after migration 007 DDL; gate **POST** until CA memo seeds statutory config.

## Checkout fields (quote / hold / booking 201 & 409)

- `platform_fee_gross`, `total_charged_online` (= `amount_due_online` + fee)
- `tax_statutory_config_id`, `tax_commercial_config_id`
- **Razorpay order = `total_charged_online`**

## Build order

1. `P-ADMIN-ROLE` (P0 hotfix — Sprint 4-0)  
2. migration 007 **DDL** (no statutory seed)  
3. Phase 4: `A-TAX-CONFIG` **read** UI  
4. CA memo → `advisor_signoff_ref` → statutory seed  
5. `C-ADDR` → `users.billing_state_code`  
6. Quote/hold snapshot → booking inherits  
7. `P-IGST` → `A-TAX-CONFIG` **write** → `P-SPLITS` → `P-TDS-393`

## Launch-gate tests

`LG-statutory-grant`, `LG-quote-snapshot`, `LG-admin-rejects-statutory`, `LG-igst-interstate`, `LG-idempotent-replay` — see PDF §13.

Full API JSON shapes and migration ordering: source `A-TAX-CONFIG_spec.md` (merged into track files above).
