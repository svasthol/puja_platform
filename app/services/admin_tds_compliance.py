"""Admin TDS compliance backlog, FY reconcile, offline-collection corrections (§0.S)."""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status as http
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import tds_accrual_service
from app.services.tds_ledger_net_sql import LEDGER_GROSS_NET_EXPR, LEDGER_TDS_NET_EXPR


async def _intents_table_exists(db: AsyncSession) -> bool:
    row = (
        await db.execute(
            text(
                """
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = 'pujari_tds_accrual_intents'
                """
            )
        )
    ).scalar_one_or_none()
    return row is not None


async def compliance_backlog(
    db: AsyncSession, *, limit: int = 50
) -> dict[str, Any]:
    if not await _intents_table_exists(db):
        return {
            "parked_count": 0,
            "pending_count": 0,
            "failed_count": 0,
            "intents": [],
            "pujari_readiness": [],
        }

    counts = (
        await db.execute(
            text(
                """
                SELECT
                    count(*) FILTER (WHERE status = 'parked'),
                    count(*) FILTER (WHERE status = 'pending'),
                    count(*) FILTER (WHERE status = 'failed')
                FROM pujari_tds_accrual_intents
                """
            )
        )
    ).one()

    intent_rows = (
        await db.execute(
            text(
                """
                SELECT id AS intent_id, booking_id, pujari_id, status, park_reason,
                       gross_amount, collected_at, snapshot_entity_type,
                       snapshot_pan_on_file, attempt_count, last_error, created_at
                FROM pujari_tds_accrual_intents
                WHERE status IN ('parked', 'failed', 'pending')
                ORDER BY
                    CASE status WHEN 'failed' THEN 0 WHEN 'parked' THEN 1 ELSE 2 END,
                    created_at
                LIMIT :lim
                """
            ),
            {"lim": limit},
        )
    ).mappings().all()

    readiness = (
        await db.execute(
            text(
                """
                SELECT p.id AS pujari_id,
                       p.entity_type,
                       (p.pan_hash IS NOT NULL) AS pan_on_file,
                       p.pan_status,
                       count(*) FILTER (WHERE i.status = 'parked') AS parked_intents,
                       count(*) FILTER (WHERE i.status = 'pending') AS pending_intents
                FROM pujaris p
                LEFT JOIN pujari_tds_accrual_intents i ON i.pujari_id = p.id
                    AND i.status IN ('parked', 'pending')
                GROUP BY p.id, p.entity_type, p.pan_hash, p.pan_status
                HAVING count(*) FILTER (WHERE i.status IN ('parked', 'pending')) > 0
                    OR p.entity_type IS NULL
                    OR p.pan_hash IS NULL
                ORDER BY parked_intents DESC, pending_intents DESC
                LIMIT :lim
                """
            ),
            {"lim": limit},
        )
    ).mappings().all()

    return {
        "parked_count": counts[0],
        "pending_count": counts[1],
        "failed_count": counts[2],
        "intents": [dict(r) for r in intent_rows],
        "pujari_readiness": [dict(r) for r in readiness],
    }


async def fy_reconcile(db: AsyncSession) -> dict[str, Any]:
    """FY accumulator vs ledger net (gross + TDS); no statutory recompute."""
    gross_rows = (
        await db.execute(
            text(
                f"""
                SELECT ty.pujari_id,
                       ty.fy_start,
                       ty.gross_facilitation AS accumulator_gross,
                       {LEDGER_GROSS_NET_EXPR} AS ledger_net
                FROM pujari_tax_year ty
                LEFT JOIN pujari_tds_facilitation_ledger l
                       ON l.pujari_id = ty.pujari_id AND l.fy_start = ty.fy_start
                GROUP BY ty.pujari_id, ty.fy_start, ty.gross_facilitation
                HAVING ty.gross_facilitation <> {LEDGER_GROSS_NET_EXPR}
                ORDER BY ty.fy_start, ty.pujari_id
                """
            )
        )
    ).mappings().all()

    tds_rows = (
        await db.execute(
            text(
                f"""
                SELECT ty.pujari_id,
                       ty.fy_start,
                       ty.tds_accrued AS accumulator_tds,
                       {LEDGER_TDS_NET_EXPR} AS ledger_tds_net
                FROM pujari_tax_year ty
                LEFT JOIN pujari_tds_facilitation_ledger l
                       ON l.pujari_id = ty.pujari_id AND l.fy_start = ty.fy_start
                GROUP BY ty.pujari_id, ty.fy_start, ty.tds_accrued
                HAVING ty.tds_accrued <> {LEDGER_TDS_NET_EXPR}
                ORDER BY ty.fy_start, ty.pujari_id
                """
            )
        )
    ).mappings().all()

    out: list[dict[str, Any]] = []
    for r in gross_rows:
        acc = Decimal(str(r["accumulator_gross"]))
        net = Decimal(str(r["ledger_net"]))
        out.append(
            {
                "kind": "gross_facilitation",
                "pujari_id": r["pujari_id"],
                "fy_start": str(r["fy_start"]),
                "accumulator": acc,
                "ledger_net": net,
                "drift": (acc - net).quantize(Decimal("0.01")),
            }
        )
    for r in tds_rows:
        acc = Decimal(str(r["accumulator_tds"]))
        net = Decimal(str(r["ledger_tds_net"]))
        out.append(
            {
                "kind": "tds_accrued",
                "pujari_id": r["pujari_id"],
                "fy_start": str(r["fy_start"]),
                "accumulator": acc,
                "ledger_net": net,
                "drift": (acc - net).quantize(Decimal("0.01")),
            }
        )
    return {
        "green": len(gross_rows) == 0 and len(tds_rows) == 0,
        "tds_green": len(tds_rows) == 0,
        "gross_drift_count": len(gross_rows),
        "rows": out,
    }


async def correct_offline_collection(
    db: AsyncSession,
    *,
    booking_id: uuid.UUID,
    action: str,
    amount: Decimal | None,
    change_reason: str,
) -> dict[str, Any]:
    """D4 — operator correction; reverses TDS when offline collection is cleared or reduced."""
    row = (
        await db.execute(
            text(
                """
                SELECT b.id, b.pujari_id, b.amount_due_offline, b.total_amount,
                       b.balance_collected_at, b.balance_collected_amount
                FROM bookings b
                WHERE b.id = :bid
                FOR UPDATE OF b
                """
            ),
            {"bid": str(booking_id)},
        )
    ).mappings().first()
    if row is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "Booking not found.")
    if row["balance_collected_at"] is None:
        raise HTTPException(http.HTTP_409_CONFLICT, "No offline collection recorded.")

    offline_due = Decimal(str(row["amount_due_offline"] or 0))
    pujari_id = uuid.UUID(str(row["pujari_id"]))
    tds_reversal: dict | None = None
    tds_requeued = False

    if action == "clear":
        tds_reversal = await tds_accrual_service.reverse_tds_on_offline_collection_reversed(
            db, booking_id=booking_id, pujari_id=pujari_id
        )
        await db.execute(
            text(
                """
                UPDATE bookings
                SET balance_collected_at = NULL,
                    balance_collected_by = NULL,
                    balance_collection_method = NULL,
                    balance_collected_amount = NULL,
                    updated_at = now()
                WHERE id = :bid
                """
            ),
            {"bid": str(booking_id)},
        )
        if await _intents_table_exists(db):
            await db.execute(
                text(
                    """
                    DELETE FROM pujari_tds_accrual_intents
                    WHERE booking_id = :bid
                      AND status IN ('pending', 'parked', 'failed')
                    """
                ),
                {"bid": str(booking_id)},
            )
        return {
            "booking_id": booking_id,
            "balance_collected_amount": None,
            "balance_collected_at": None,
            "tds_reversal": tds_reversal,
            "tds_requeued": False,
            "change_reason": change_reason,
        }

    if action != "set_amount" or amount is None:
        raise HTTPException(http.HTTP_422_UNPROCESSABLE_ENTITY, "amount required for set_amount.")

    new_amt = amount.quantize(Decimal("0.01"))
    if new_amt <= 0 or new_amt > offline_due:
        raise HTTPException(
            http.HTTP_422_UNPROCESSABLE_ENTITY,
            "amount must be positive and not exceed offline balance due.",
        )

    old_amt = Decimal(str(row["balance_collected_amount"] or 0))
    if new_amt == old_amt:
        raise HTTPException(http.HTTP_409_CONFLICT, "Amount unchanged.")

    if new_amt < old_amt:
        tds_reversal = await tds_accrual_service.reverse_tds_on_offline_collection_reversed(
            db, booking_id=booking_id, pujari_id=pujari_id
        )

    await db.execute(
        text(
            """
            UPDATE bookings
            SET balance_collected_amount = :amt, updated_at = now()
            WHERE id = :bid
            """
        ),
        {"amt": str(new_amt), "bid": str(booking_id)},
    )

    if await _intents_table_exists(db):
        await db.execute(
            text("DELETE FROM pujari_tds_accrual_intents WHERE booking_id = :bid"),
            {"bid": str(booking_id)},
        )
        payload = await tds_accrual_service.enqueue_tds_accrual_intent(
            db,
            booking_id=booking_id,
            pujari_id=pujari_id,
            gross_amount=Decimal(str(row["total_amount"])),
            collected_at=row["balance_collected_at"],
        )
        tds_requeued = payload.get("message") == "TDS accrual queued."

    return {
        "booking_id": booking_id,
        "balance_collected_amount": new_amt,
        "balance_collected_at": str(row["balance_collected_at"]),
        "tds_reversal": tds_reversal,
        "tds_requeued": tds_requeued,
        "change_reason": change_reason,
    }
