"""Read-only CA export: per-pujari ledger TDS net for a calendar month or Indian FY quarter."""
from __future__ import annotations

import argparse
import calendar
import csv
import datetime as dt
import os
import sys
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.pricing_tds_v3 import deposit_round_inr  # noqa: E402
from app.services.tds_ledger_net_sql import (  # noqa: E402
    LEDGER_GROSS_NET_EXPR,
    LEDGER_TDS_NET_EXPR,
)

try:
    import psycopg
except ImportError:
    print("psycopg not installed", file=sys.stderr)
    sys.exit(1)

DEFAULT_SECTION = os.environ.get("TDS_26Q_SECTION", "194-O")
_PAISE = Decimal("0.01")


def _sync_url() -> str:
    url = os.environ.get("DATABASE_URL", "postgresql://postgres@127.0.0.1:5432/Mana_Guruji")
    return url.replace("postgresql+psycopg://", "postgresql://").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


def _parse_month(value: str) -> tuple[dt.datetime, dt.datetime]:
    year, month = map(int, value.split("-", 1))
    if month < 1 or month > 12:
        raise ValueError("month must be 01–12")
    last_day = calendar.monthrange(year, month)[1]
    start = dt.datetime(year, month, 1, tzinfo=dt.UTC)
    end = dt.datetime(year, month, last_day, 23, 59, 59, 999999, tzinfo=dt.UTC)
    return start, end


def _parse_fy_quarter(fy: int, quarter: int) -> tuple[dt.datetime, dt.datetime]:
    if quarter not in (1, 2, 3, 4):
        raise ValueError("quarter must be 1–4 (Indian FY: Q1=Apr–Jun … Q4=Jan–Mar)")
    quarter_starts = [
        dt.datetime(fy, 4, 1, tzinfo=dt.UTC),
        dt.datetime(fy, 7, 1, tzinfo=dt.UTC),
        dt.datetime(fy, 10, 1, tzinfo=dt.UTC),
        dt.datetime(fy + 1, 1, 1, tzinfo=dt.UTC),
    ]
    start = quarter_starts[quarter - 1]
    if quarter == 4:
        end = dt.datetime(fy + 1, 4, 1, tzinfo=dt.UTC) - dt.timedelta(microseconds=1)
    else:
        end = quarter_starts[quarter] - dt.timedelta(microseconds=1)
    return start, end


def _period_bounds(args: argparse.Namespace) -> tuple[dt.datetime, dt.datetime]:
    if args.month:
        return _parse_month(args.month)
    if args.fy is not None and args.quarter is not None:
        return _parse_fy_quarter(args.fy, args.quarter)
    raise SystemExit("Provide --month=YYYY-MM or both --fy=YYYY and --quarter=N")


def fetch_export_rows(
    conn: psycopg.Connection, *, period_start: dt.datetime, period_end: dt.datetime
) -> list[dict[str, str]]:
    gross_expr = LEDGER_GROSS_NET_EXPR.strip()
    tds_expr = LEDGER_TDS_NET_EXPR.strip()
    sql = f"""
        SELECT
            p.id::text AS pujari_id,
            u.full_name AS pujari_name,
            u.phone AS phone,
            {gross_expr} AS amount_on_which_tds_deducted,
            {tds_expr} AS tds_deducted,
            MIN(l.created_at) AS first_txn_date,
            MAX(l.created_at) AS last_txn_date
        FROM pujari_tds_facilitation_ledger l
        JOIN pujaris p ON p.id = l.pujari_id
        JOIN users u ON u.id = p.user_id
        WHERE l.created_at >= %(start)s AND l.created_at <= %(end)s
        GROUP BY p.id, u.full_name, u.phone
        HAVING {tds_expr} > 0
        ORDER BY u.full_name, p.id
    """
    with conn.cursor() as cur:
        cur.execute(
            sql,
            {"start": period_start, "end": period_end},
        )
        rows = cur.fetchall()
    out: list[dict[str, str]] = []
    for row in rows:
        amount = Decimal(str(row[3])).quantize(_PAISE)
        tds = Decimal(str(row[4])).quantize(_PAISE)
        first_dt = row[5]
        last_dt = row[6]
        out.append(
            {
                "pujari_id": row[0],
                "pujari_name": row[1] or "",
                "phone": row[2] or "",
                "PAN": "",
                "section": DEFAULT_SECTION,
                "amount_on_which_tds_deducted": str(amount),
                "tds_deducted": str(tds),
                "first_txn_date": first_dt.date().isoformat() if first_dt else "",
                "last_txn_date": last_dt.date().isoformat() if last_dt else "",
                "challan_reference": "",
            }
        )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export read-only 26Q worksheet CSV from TDS facilitation ledger net"
    )
    parser.add_argument("--month", metavar="YYYY-MM", help="Calendar month filter on ledger.created_at")
    parser.add_argument("--fy", type=int, help="Indian FY start year (e.g. 2025 for FY 2025–26)")
    parser.add_argument("--quarter", type=int, help="Quarter 1–4 within --fy")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="CSV path (default: stdout)",
    )
    args = parser.parse_args()
    if bool(args.month) == bool(args.fy is not None or args.quarter is not None):
        if args.month and (args.fy is not None or args.quarter is not None):
            parser.error("Use either --month or --fy/--quarter, not both")
        if not args.month and (args.fy is None or args.quarter is None):
            parser.error("Provide --month=YYYY-MM or both --fy and --quarter")

    period_start, period_end = _period_bounds(args)

    with psycopg.connect(_sync_url()) as conn:
        rows = fetch_export_rows(conn, period_start=period_start, period_end=period_end)

    fieldnames = [
        "pujari_id",
        "pujari_name",
        "phone",
        "PAN",
        "section",
        "amount_on_which_tds_deducted",
        "tds_deducted",
        "first_txn_date",
        "last_txn_date",
        "challan_reference",
    ]
    total_tds = sum(Decimal(r["tds_deducted"]) for r in rows)
    deposit_total = deposit_round_inr(total_tds)

    out_stream = open(args.output, "w", newline="", encoding="utf-8") if args.output else sys.stdout
    try:
        writer = csv.DictWriter(out_stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    finally:
        if args.output:
            out_stream.close()

    print(
        f"# total_tds_deducted={total_tds.quantize(_PAISE)} "
        f"deposit_round_inr={deposit_total.quantize(_PAISE)} "
        f"period={period_start.date()}..{period_end.date()} rows={len(rows)}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
