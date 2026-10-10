"""One-off: migration 025 + pujari PAN/entity_type readiness + TDS v3 reconcile."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

try:
    import psycopg
except ImportError:
    print("psycopg not installed", file=sys.stderr)
    sys.exit(1)


def _sync_url() -> str:
    url = os.environ.get("DATABASE_URL", "postgresql://postgres@127.0.0.1:5432/Mana_Guruji")
    return url.replace("postgresql+psycopg://", "postgresql://").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


def _ledger_tds_net_sql(alias: str = "l") -> str:
    return f"""COALESCE(SUM(
        CASE
            WHEN {alias}.entry_type IN ('accrual', 'catch_up') THEN {alias}.tds_amount
            WHEN {alias}.entry_type = 'reversal' THEN -{alias}.tds_amount
            ELSE 0
        END
    ), 0)"""


def main() -> None:
    parser = argparse.ArgumentParser(description="TDS launch / v3 readiness report")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 if v3 schema incomplete or any FY tds_accrued != ledger TDS net",
    )
    args = parser.parse_args()
    blockers: list[str] = []

    with psycopg.connect(_sync_url()) as conn:
        with conn.cursor() as cur:
            checks = [
                ("bookings.booking_fee", "bookings", "booking_fee"),
                ("pujaris.pan_hash", "pujaris", "pan_hash"),
                ("pujaris.entity_type", "pujaris", "entity_type"),
                ("bookings.tds_snapshot_entity_type", "bookings", "tds_snapshot_entity_type"),
                ("bookings.tds_snapshot_pan_on_file", "bookings", "tds_snapshot_pan_on_file"),
            ]
            print("=== Migration 025/026 column checks ===")
            for label, table, col in checks:
                cur.execute(
                    """
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema='public' AND table_name=%s AND column_name=%s
                    """,
                    (table, col),
                )
                ok = cur.fetchone() is not None
                print(f"  {label}: {'YES' if ok else 'NO'}")
                if not ok and args.strict:
                    blockers.append(f"missing column {table}.{col}")

            for table in ("pujari_tax_year", "pujari_tds_facilitation_ledger"):
                cur.execute(
                    """
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema='public' AND table_name=%s
                    """,
                    (table,),
                )
                ok = cur.fetchone() is not None
                print(f"  table {table}: {'YES' if ok else 'NO'}")
                if not ok and args.strict:
                    blockers.append(f"missing table {table}")

            v3_cols = [
                ("pujari_tax_year.deduction_latched", "pujari_tax_year", "deduction_latched"),
                ("bookings.tds_facilitation_fy_applied_at", "bookings", "tds_facilitation_fy_applied_at"),
                ("bookings.tds_liability_inr", "bookings", "tds_liability_inr"),
                ("bookings.tds_online_charge_closed_at", "bookings", "tds_online_charge_closed_at"),
                ("ledger.refund_reference", "pujari_tds_facilitation_ledger", "refund_reference"),
            ]
            print()
            print("=== TDS v3 migration chain 028–034 ===")
            for label, table, col in v3_cols:
                cur.execute(
                    """
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema='public' AND table_name=%s AND column_name=%s
                    """,
                    (table, col),
                )
                ok = cur.fetchone() is not None
                print(f"  {label}: {'YES' if ok else 'NO — run scripts/apply_migrations_028_032.py'}")
                if not ok and args.strict:
                    blockers.append(f"missing v3 column {table}.{col}")

            cur.execute("SELECT 1 FROM platform_settings WHERE key='tds_facilitation'")
            print(f"  platform_settings.tds_facilitation: {'YES' if cur.fetchone() else 'NO'}")

            print()
            print("=== Pujaris (PAN + entity_type) ===")
            # No PII (DPDP): pujari id prefix + tax fields only — never phone / PAN.
            cur.execute(
                """
                SELECT p.id::text, p.verification_status,
                       p.entity_type,
                       CASE WHEN p.pan_hash IS NOT NULL THEN 'yes' ELSE 'no' END
                FROM pujaris p
                ORDER BY p.id
                LIMIT 25
                """
            )
            rows = cur.fetchall()
            if not rows:
                print("  (no pujaris)")
            for r in rows:
                print(f"  {r[0][:8]}... verified={r[1]} entity_type={r[2]} pan={r[3]}")

            cur.execute(
                """
                SELECT count(*),
                       count(*) FILTER (WHERE entity_type IS NOT NULL),
                       count(*) FILTER (WHERE pan_hash IS NOT NULL),
                       count(*) FILTER (WHERE entity_type IS NOT NULL AND pan_hash IS NOT NULL)
                FROM pujaris
                """
            )
            t, et, pan, ready = cur.fetchone()
            print()
            print(f"  total={t} with_entity_type={et} with_pan={pan} tds_ready_both={ready}")

            cur.execute("SELECT count(*) FROM pujari_tax_year")
            fy = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM pujari_tds_facilitation_ledger")
            led = cur.fetchone()[0]
            print()
            print(f"=== TDS data: fy_rows={fy} ledger_rows={led} ===")

            cur.execute(
                """
                SELECT 1 FROM information_schema.tables
                WHERE table_schema='public' AND table_name='pujari_tds_recovery'
                """
            )
            if cur.fetchone():
                cur.execute(
                    """
                    SELECT COALESCE(SUM(tds_amount), 0),
                           count(*) FILTER (WHERE status = 'pending')
                    FROM pujari_tds_recovery
                    WHERE status = 'pending'
                    """
                )
                rec_sum, rec_n = cur.fetchone()
                print()
                print("=== TDS v3 pending recovery (accept charge failed / stub off) ===")
                print(f"  pending_rows={rec_n} sum_tds_amount=Rs {float(rec_sum or 0):,.2f}")
            else:
                print()
                print("=== TDS v3 pending recovery ===")
                print("  table missing — run migration 030")

            net_expr = _ledger_tds_net_sql("l")
            cur.execute(
                """
                SELECT count(DISTINCT ty.pujari_id)
                FROM pujari_tax_year ty
                JOIN pujaris p ON p.id = ty.pujari_id
                WHERE ty.gross_facilitation > 500000
                  AND p.entity_type IN ('individual', 'huf')
                  AND (
                        p.pan_hash IS NULL
                        OR COALESCE(p.pan_status, 'unverified') <> 'operative'
                      )
                """
            )
            over5l_no_op = cur.fetchone()[0]
            print()
            print("=== TDS v3 exposure monitor (statutory shape) ===")
            print(
                f"  [1] Individual/HUF FY gross > Rs 5,00,000 without operative PAN: "
                f"{over5l_no_op} pujari(s)"
            )
            print(
                "      -> TDS applies only on the slice above Rs 5L; fail-safe 5% when latched "
                "without operative PAN (not 5% on all GMV below threshold)."
            )
            cur.execute(
                """
                SELECT ty.pujari_id::text, ty.gross_facilitation, ty.tds_accrued
                FROM pujari_tax_year ty
                JOIN pujaris p ON p.id = ty.pujari_id
                WHERE ty.gross_facilitation > 500000
                  AND p.entity_type IN ('individual', 'huf')
                  AND (
                        p.pan_hash IS NULL
                        OR COALESCE(p.pan_status, 'unverified') <> 'operative'
                      )
                ORDER BY ty.gross_facilitation DESC
                LIMIT 15
                """
            )
            for pid, gross, tds_acc in cur.fetchall():
                print(
                    f"      {pid[:8]}... fy_gross=Rs {float(gross):,.2f} "
                    f"tds_accrued=Rs {float(tds_acc or 0):,.2f}"
                )

            cur.execute(
                """
                SELECT p.id::text, COALESCE(SUM(b.balance_collected_amount), 0) AS gross
                FROM pujaris p
                JOIN bookings b ON b.pujari_id = p.id
                WHERE p.pan_hash IS NOT NULL
                  AND COALESCE(p.pan_status, 'unverified') = 'operative'
                  AND p.entity_type IN ('individual', 'huf')
                  AND b.balance_collected_at IS NOT NULL
                GROUP BY p.id
                HAVING COALESCE(SUM(b.balance_collected_amount), 0) >= 450000
                ORDER BY gross DESC
                LIMIT 25
                """
            )
            near = cur.fetchall()
            print(
                f"  [2] Operative PAN individual/HUF offline collected >= Rs 4,50,000: {len(near)}"
            )
            for pid, gross in near:
                flag = "OVER 5L" if float(gross) >= 500000 else "approaching"
                print(f"      {pid[:8]}... gross=Rs {float(gross):,.2f} [{flag}]")

            cur.execute(
                f"""
                SELECT ty.pujari_id::text, ty.fy_start::text,
                       ty.tds_accrued,
                       {net_expr} AS ledger_tds_net
                FROM pujari_tax_year ty
                LEFT JOIN pujari_tds_facilitation_ledger l
                       ON l.pujari_id = ty.pujari_id AND l.fy_start = ty.fy_start
                GROUP BY ty.pujari_id, ty.fy_start, ty.tds_accrued
                HAVING ty.tds_accrued <> {net_expr}
                ORDER BY ty.fy_start, ty.pujari_id
                """
            )
            tds_drift = cur.fetchall()
            print()
            if tds_drift:
                print(
                    f"=== TDS RECONCILE DRIFT (BLOCKER): {len(tds_drift)} FY row(s) "
                    f"tds_accrued != ledger TDS net ==="
                )
                for pid, fystart, acc, ledger_net in tds_drift:
                    drift = float(acc or 0) - float(ledger_net or 0)
                    print(
                        f"  {pid[:8]}... fy={fystart} tds_accrued={acc} "
                        f"ledger_tds_net={ledger_net} drift={drift:,.2f}"
                    )
                if args.strict:
                    blockers.append(f"tds reconcile drift: {len(tds_drift)} row(s)")
            else:
                print("=== Reconcile: tds_accrued == ledger TDS net (green) ===")

            # ---- FY turnover vs ledger taxable net (v3: expect drift on crossing bookings) ----
            cur.execute(
                """
                SELECT ty.pujari_id::text, ty.fy_start::text,
                       ty.gross_facilitation,
                       COALESCE(SUM(
                           CASE
                               WHEN l.entry_type IN ('accrual', 'catch_up') THEN l.gross_amount
                               WHEN l.entry_type = 'reversal' THEN -l.gross_amount
                               ELSE 0
                           END
                       ), 0) AS ledger_taxable_net
                FROM pujari_tax_year ty
                LEFT JOIN pujari_tds_facilitation_ledger l
                       ON l.pujari_id = ty.pujari_id AND l.fy_start = ty.fy_start
                GROUP BY ty.pujari_id, ty.fy_start, ty.gross_facilitation
                HAVING ty.gross_facilitation <> COALESCE(SUM(
                           CASE
                               WHEN l.entry_type IN ('accrual', 'catch_up') THEN l.gross_amount
                               WHEN l.entry_type = 'reversal' THEN -l.gross_amount
                               ELSE 0
                           END
                       ), 0)
                """
            )
            gross_drift = cur.fetchall()
            print()
            if gross_drift:
                print(
                    f"=== FY turnover vs ledger taxable net: {len(gross_drift)} row(s) differ "
                    f"(expected v3 when accept FY turnover > balance ledger slice) ==="
                )
                for pid, fystart, acc, ledger_net in gross_drift[:10]:
                    print(
                        f"  {pid[:8]}... fy={fystart} gross_facilitation={acc} "
                        f"ledger_taxable_net={ledger_net}"
                    )
            else:
                print("=== FY turnover == ledger taxable net (all rows) ===")

            # ---- Classification snapshot coverage (§0.L-4) ----
            cur.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema='public' AND table_name='bookings'
                  AND column_name='tds_snapshot_pan_on_file'
                """
            )
            if cur.fetchone():
                cur.execute(
                    """
                    SELECT count(*) FILTER (WHERE balance_collected_at IS NOT NULL),
                           count(*) FILTER (
                               WHERE balance_collected_at IS NOT NULL
                                 AND tds_snapshot_pan_on_file IS NOT NULL
                           ),
                           count(*) FILTER (
                               WHERE balance_collected_at IS NOT NULL
                                 AND tds_snapshot_pan_on_file IS NULL
                           )
                    FROM bookings
                    """
                )
                collected, snap_ok, snap_missing = cur.fetchone()
                print()
                print("=== Classification snapshot coverage (§0.L-4) ===")
                print(f"  collections={collected} with_snapshot={snap_ok} missing_snapshot={snap_missing}")
                if snap_missing:
                    print(
                        "  WARNING: missing snapshots — catch_up may fall back to current classification"
                    )
            else:
                print()
                print("=== Classification snapshot coverage (§0.L-4) ===")
                print("  migration_026 not applied — run: python scripts/apply_migration_026.py")

            cur.execute(
                """
                SELECT 1 FROM information_schema.tables
                WHERE table_schema='public' AND table_name='pujari_tds_accrual_intents'
                """
            )
            if cur.fetchone():
                cur.execute(
                    """
                    SELECT status, count(*),
                           min(created_at) FILTER (WHERE status = 'parked')
                    FROM pujari_tds_accrual_intents
                    GROUP BY status
                    """
                )
                print()
                print("=== Accrual intent backlog (§0.S) ===")
                for status, cnt, oldest_parked in cur.fetchall():
                    extra = f" oldest_parked={oldest_parked}" if status == "parked" and oldest_parked else ""
                    print(f"  {status}: {cnt}{extra}")
                cur.execute(
                    """
                    SELECT count(*) FROM pujari_tds_accrual_intents
                    WHERE status IN ('pending', 'parked')
                    """
                )
                backlog_total = cur.fetchone()[0]
                print(f"  pending+parked total: {backlog_total} (D6 sizing — worker caps 50 pujaris × 25 intents/tick)")

    if blockers:
        print()
        print("=== STRICT: FAILED ===")
        for b in blockers:
            print(f"  - {b}")
        sys.exit(1)
    if args.strict:
        print()
        print("=== STRICT: OK (zero TDS drift, schema complete) ===")


if __name__ == "__main__":
    main()
