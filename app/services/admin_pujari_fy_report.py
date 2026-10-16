"""Admin FY earnings report per pujari (ops)."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.pujari_fy_pan_gate import evaluate_fy_pan_gate
from app.services.pricing import load_tds_facilitation_config
from app.services.tds_accrual_service import fy_start_for_date


async def pujari_fy_earnings_report(
    db: AsyncSession,
    *,
    fy_start: dt.date | None = None,
    limit: int = 100,
    min_gross: Decimal | None = None,
) -> dict[str, Any]:
    """Aggregate collected facilitation gross per pujari for an Indian FY."""
    anchor = fy_start or fy_start_for_date(dt.date.today())
    params: dict[str, Any] = {"fy_start": anchor, "fy_end": _fy_end(anchor), "lim": limit}
    having = ""
    if min_gross is not None:
        params["min_gross"] = str(min_gross.quantize(Decimal("0.01")))
        having = "HAVING COALESCE(SUM(b.balance_collected_amount), 0) >= :min_gross"

    rows = (
        await db.execute(
            text(
                f"""
                SELECT
                    pj.id AS pujari_id,
                    u.full_name,
                    pj.entity_type,
                    pj.pan_hash IS NOT NULL AS pan_on_file,
                    (pj.pan_status = 'operative') AS pan_operative,
                    pj.pan_status,
                    COUNT(*) FILTER (WHERE b.balance_collected_at IS NOT NULL)::int AS collections_count,
                    COALESCE(SUM(b.balance_collected_amount), 0) AS fy_collected_gross,
                    COALESCE(SUM(b.total_amount), 0) AS fy_gross_facilitation,
                    COALESCE(pty.gross_facilitation, 0) AS fy_ledger_gross,
                    COALESCE(pty.tds_accrued, 0) AS tds_accrued
                FROM pujaris pj
                JOIN users u ON u.id = pj.user_id
                LEFT JOIN bookings b
                  ON b.pujari_id = pj.id
                 AND b.balance_collected_at IS NOT NULL
                 AND b.balance_collected_at >= :fy_start
                 AND b.balance_collected_at < :fy_end
                LEFT JOIN pujari_tax_year pty
                  ON pty.pujari_id = pj.id AND pty.fy_start = :fy_start
                GROUP BY pj.id, u.full_name, pj.entity_type, pj.pan_hash, pj.pan_status,
                         pty.gross_facilitation, pty.tds_accrued
                {having}
                ORDER BY fy_collected_gross DESC, u.full_name
                LIMIT :lim
                """
            ),
            params,
        )
    ).mappings().all()

    cfg = await load_tds_facilitation_config(db)
    pujaris_out = []
    for r in rows:
        gross = Decimal(str(r["fy_gross_facilitation"])).quantize(Decimal("0.01"))
        gate = evaluate_fy_pan_gate(
            fy_gross_inr=gross,
            pan_on_file=bool(r["pan_operative"]),
            entity_type=r["entity_type"],
            cfg=cfg,
        )
        pujaris_out.append(
            {
                "pujari_id": str(r["pujari_id"]),
                "full_name": r["full_name"],
                "entity_type": r["entity_type"],
                "pan_on_file": bool(r["pan_on_file"]),
                "pan_operative": bool(r["pan_operative"]),
                "pan_status": r["pan_status"],
                "collections_count": int(r["collections_count"]),
                "fy_collected_gross_inr": str(
                    Decimal(str(r["fy_collected_gross"])).quantize(Decimal("0.01"))
                ),
                "fy_gross_facilitation_inr": str(gross),
                "fy_ledger_gross_inr": str(
                    Decimal(str(r["fy_ledger_gross"])).quantize(Decimal("0.01"))
                ),
                "tds_accrued_inr": str(
                    Decimal(str(r["tds_accrued"])).quantize(Decimal("0.01"))
                ),
                "fy_pan_gate_level": gate.level,
            }
        )

    return {
        "fy_start": anchor.isoformat(),
        "fy_end_exclusive": _fy_end(anchor).isoformat(),
        "pujaris": pujaris_out,
    }


def _fy_end(fy_start: dt.date) -> dt.date:
    return dt.date(fy_start.year + 1, 4, 1)
