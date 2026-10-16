"""Admin FY reconcile troubleshoot — compare card, ledger, and bookings (read + safe repair)."""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any, Literal

from fastapi import HTTPException, status as http
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.admin_tds_compliance import _intents_table_exists, fy_reconcile
from app.services.tds_accrual_service import (
    enqueue_tds_accrual_intent,
    fy_start_for_date,
    lookup_accrual_for_booking,
    process_pending_accrual_intents_for_pujari,
    reconcile_failed_accrual_intents,
)
from app.services.tds_ledger_net_sql import LEDGER_GROSS_NET_EXPR, LEDGER_TDS_NET_EXPR

_MAX_BOOKING_FINDINGS = 50
_MAX_SAFE_FIX_BOOKINGS = 25
_MONEY = Decimal("0.01")

TaxStatus = Literal["match", "fixable", "manual", "accrual_disabled"]
GrossStatus = Literal["match", "expected_v3", "investigate", "no_tax_year_row"]


def _fy_end(fy_start: dt.date) -> dt.date:
    return dt.date(fy_start.year + 1, 4, 1)


def _q(value: Decimal) -> Decimal:
    return value.quantize(_MONEY)


async def _load_tax_year(
    db: AsyncSession, *, pujari_id: uuid.UUID, fy_start: dt.date
) -> dict[str, Decimal] | None:
    row = (
        await db.execute(
            text(
                """
                SELECT gross_facilitation, tds_accrued
                FROM pujari_tax_year
                WHERE pujari_id = :pid AND fy_start = :fy
                """
            ),
            {"pid": str(pujari_id), "fy": fy_start},
        )
    ).mappings().first()
    if row is None:
        return None
    return {
        "gross_facilitation": _q(Decimal(str(row["gross_facilitation"]))),
        "tds_accrued": _q(Decimal(str(row["tds_accrued"]))),
    }


async def _ledger_nets(
    db: AsyncSession, *, pujari_id: uuid.UUID, fy_start: dt.date
) -> dict[str, Decimal]:
    row = (
        await db.execute(
            text(
                f"""
                SELECT
                    {LEDGER_GROSS_NET_EXPR.replace('l.', 'l.')} AS ledger_gross,
                    {LEDGER_TDS_NET_EXPR.replace('l.', 'l.')} AS ledger_tds
                FROM pujari_tds_facilitation_ledger l
                WHERE l.pujari_id = :pid AND l.fy_start = :fy
                """
            ),
            {"pid": str(pujari_id), "fy": fy_start},
        )
    ).mappings().first()
    if row is None:
        return {"ledger_gross": Decimal("0"), "ledger_tds": Decimal("0")}
    return {
        "ledger_gross": _q(Decimal(str(row["ledger_gross"]))),
        "ledger_tds": _q(Decimal(str(row["ledger_tds"]))),
    }


async def _booking_rollups(
    db: AsyncSession, *, pujari_id: uuid.UUID, fy_start: dt.date, fy_end: dt.date
) -> dict[str, Any]:
    accept = (
        await db.execute(
            text(
                """
                SELECT
                    COUNT(*)::int AS accept_count,
                    COALESCE(SUM(total_amount), 0) AS turnover_at_accept,
                    COALESCE(SUM(tds_liability_inr), 0) AS tds_at_accept
                FROM bookings
                WHERE pujari_id = :pid
                  AND tds_facilitation_fy_applied_at IS NOT NULL
                  AND tds_facilitation_fy_applied_at >= :fy_start
                  AND tds_facilitation_fy_applied_at < :fy_end
                """
            ),
            {"pid": str(pujari_id), "fy_start": fy_start, "fy_end": fy_end},
        )
    ).mappings().one()

    collected = (
        await db.execute(
            text(
                """
                SELECT
                    COUNT(*)::int AS collected_count,
                    COALESCE(SUM(balance_collected_amount), 0) AS collected_gross,
                    COALESCE(SUM(tds_liability_inr), 0) AS tds_on_collected_bookings
                FROM bookings
                WHERE pujari_id = :pid
                  AND balance_collected_at IS NOT NULL
                  AND balance_collected_at >= :fy_start
                  AND balance_collected_at < :fy_end
                """
            ),
            {"pid": str(pujari_id), "fy_start": fy_start, "fy_end": fy_end},
        )
    ).mappings().one()

    ledger_materialized = (
        await db.execute(
            text(
                """
                SELECT COALESCE(SUM(b.tds_liability_inr), 0) AS tds_with_ledger
                FROM bookings b
                WHERE b.pujari_id = :pid
                  AND b.balance_collected_at >= :fy_start
                  AND b.balance_collected_at < :fy_end
                  AND EXISTS (
                      SELECT 1 FROM pujari_tds_facilitation_ledger l
                      WHERE l.booking_id = b.id AND l.entry_type = 'accrual'
                  )
                """
            ),
            {"pid": str(pujari_id), "fy_start": fy_start, "fy_end": fy_end},
        )
    ).scalar_one()

    return {
        "accept_count": int(accept["accept_count"]),
        "turnover_at_accept_inr": _q(Decimal(str(accept["turnover_at_accept"]))),
        "tds_at_accept_inr": _q(Decimal(str(accept["tds_at_accept"]))),
        "collected_count": int(collected["collected_count"]),
        "collected_gross_inr": _q(Decimal(str(collected["collected_gross"]))),
        "tds_on_collected_bookings_inr": _q(Decimal(str(collected["tds_on_collected_bookings"]))),
        "tds_on_collected_with_ledger_inr": _q(Decimal(str(ledger_materialized))),
    }


async def _booking_findings(
    db: AsyncSession, *, pujari_id: uuid.UUID, fy_start: dt.date, fy_end: dt.date
) -> list[dict[str, Any]]:
    intent_join = ""
    intent_cols = "NULL::varchar AS intent_status, NULL::varchar AS park_reason, NULL::text AS last_error,"
    if await _intents_table_exists(db):
        intent_join = "LEFT JOIN pujari_tds_accrual_intents i ON i.booking_id = b.id"
        intent_cols = """
                       i.status AS intent_status,
                       i.park_reason,
                       i.last_error,
        """
    rows = (
        await db.execute(
            text(
                f"""
                SELECT b.id AS booking_id,
                       b.total_amount,
                       b.balance_collected_at,
                       b.tds_facilitation_fy_applied_at,
                       b.tds_liability_inr,
                       {intent_cols}
                       EXISTS (
                           SELECT 1 FROM pujari_tds_facilitation_ledger l
                           WHERE l.booking_id = b.id AND l.entry_type = 'accrual'
                       ) AS has_ledger
                FROM bookings b
                {intent_join}
                WHERE b.pujari_id = :pid
                  AND (
                      (b.tds_facilitation_fy_applied_at >= :fy_start
                       AND b.tds_facilitation_fy_applied_at < :fy_end)
                      OR (b.balance_collected_at >= :fy_start
                          AND b.balance_collected_at < :fy_end)
                  )
                ORDER BY COALESCE(b.balance_collected_at, b.tds_facilitation_fy_applied_at) DESC NULLS LAST
                LIMIT :lim
                """
            ),
            {
                "pid": str(pujari_id),
                "fy_start": fy_start,
                "fy_end": fy_end,
                "lim": _MAX_BOOKING_FINDINGS,
            },
        )
    ).mappings().all()

    out: list[dict[str, Any]] = []
    for r in rows:
        bid = uuid.UUID(str(r["booking_id"]))
        issue: str | None = None
        if r["balance_collected_at"] and r["tds_facilitation_fy_applied_at"] and not r["has_ledger"]:
            issue = "collected_no_ledger"
        elif r["balance_collected_at"] and not r["tds_facilitation_fy_applied_at"]:
            issue = "collected_no_accept_snapshot"
        elif not r["balance_collected_at"] and r["tds_facilitation_fy_applied_at"]:
            issue = "accepted_not_collected"
        if r["intent_status"] in ("failed", "parked"):
            issue = issue or f"intent_{r['intent_status']}"

        if issue is None:
            continue
        out.append(
            {
                "booking_id": bid,
                "issue_code": issue,
                "total_amount_inr": str(_q(Decimal(str(r["total_amount"] or 0)))),
                "tds_liability_inr": str(_q(Decimal(str(r["tds_liability_inr"] or 0)))),
                "intent_status": r["intent_status"],
                "park_reason": r["park_reason"],
                "last_error": r["last_error"],
            }
        )
    return out


def _classify_tax(
    *,
    card_tds: Decimal,
    ledger_tds: Decimal,
    tds_at_accept: Decimal,
    findings: list[dict[str, Any]],
    accrual_enabled: bool,
) -> TaxStatus:
    if not accrual_enabled:
        return "accrual_disabled"
    if abs(card_tds - ledger_tds) <= _MONEY:
        return "match"
    fixable_codes = {"collected_no_ledger", "intent_failed", "intent_parked", "intent_pending"}
    if any(f["issue_code"] in fixable_codes or f["issue_code"].startswith("intent_") for f in findings):
        if any(f["issue_code"] == "collected_no_ledger" for f in findings):
            return "fixable"
        if any(f["issue_code"].startswith("intent_") for f in findings):
            return "fixable"
    if abs(card_tds - tds_at_accept) <= _MONEY and any(
        f["issue_code"] == "collected_no_ledger" for f in findings
    ):
        return "fixable"
    return "manual"


def _classify_gross(
    *,
    card_gross: Decimal,
    ledger_gross: Decimal,
    turnover_at_accept: Decimal,
) -> GrossStatus:
    if abs(card_gross - ledger_gross) <= _MONEY:
        return "match"
    if abs(card_gross - turnover_at_accept) <= _MONEY and ledger_gross < card_gross:
        return "expected_v3"
    if turnover_at_accept == 0 and card_gross == 0:
        return "match"
    if abs(card_gross - turnover_at_accept) > _MONEY:
        return "investigate"
    if ledger_gross < card_gross:
        return "expected_v3"
    return "investigate"


def _messages(
    *,
    tax_status: TaxStatus,
    gross_status: GrossStatus,
    tax_drift: Decimal,
    gross_drift: Decimal,
) -> list[str]:
    msgs: list[str] = []
    if tax_status == "match":
        msgs.append("Tax (TDS): yearly card matches the tax diary — no tax reconcile action.")
    elif tax_status == "accrual_disabled":
        msgs.append("TDS accrual is off in API config — ledger may be empty while the card has accept-time totals.")
    elif tax_status == "fixable":
        msgs.append(
            "Tax (TDS): mismatch likely from missing diary lines or backlog — try Safe fix "
            "(re-queues accrual for collected bookings only)."
        )
    else:
        msgs.append(
            "Tax (TDS): card and diary disagree and auto-fix cannot explain it — engineering or manual review."
        )

    if gross_status == "match":
        msgs.append("Business (gross): card matches diary taxable-base sum.")
    elif gross_status == "expected_v3":
        msgs.append(
            "Business (gross): card reflects full FY puja turnover; diary sums taxable base only — "
            f"drift ₹{gross_drift} is often normal in TDS v3 (not necessarily a bug)."
        )
    elif gross_status == "investigate":
        msgs.append(
            "Business (gross): yearly card does not match accepted bookings turnover — check accept/FY writer path."
        )
    else:
        msgs.append("No pujari_tax_year row for this FY — partner may have no TDS FY activity yet.")
    return msgs


async def troubleshoot_fy_reconcile(
    db: AsyncSession,
    *,
    pujari_id: uuid.UUID,
    fy_start: dt.date | None = None,
) -> dict[str, Any]:
    """Read-only cross-check for one partner + Indian FY."""
    anchor = fy_start or fy_start_for_date(dt.date.today())
    fy_end = _fy_end(anchor)

    exists = (
        await db.execute(
            text("SELECT 1 FROM pujaris WHERE id = :pid"),
            {"pid": str(pujari_id)},
        )
    ).scalar_one_or_none()
    if exists is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "Pujari not found.")

    tax_year = await _load_tax_year(db, pujari_id=pujari_id, fy_start=anchor)
    nets = await _ledger_nets(db, pujari_id=pujari_id, fy_start=anchor)
    rollups = await _booking_rollups(db, pujari_id=pujari_id, fy_start=anchor, fy_end=fy_end)
    findings = await _booking_findings(
        db, pujari_id=pujari_id, fy_start=anchor, fy_end=fy_end
    )

    card_gross = tax_year["gross_facilitation"] if tax_year else Decimal("0")
    card_tds = tax_year["tds_accrued"] if tax_year else Decimal("0")
    ledger_gross = nets["ledger_gross"]
    ledger_tds = nets["ledger_tds"]
    tax_drift = _q(card_tds - ledger_tds)
    gross_drift = _q(card_gross - ledger_gross)

    accrual_on = get_settings().TDS_ACCRUAL_ENABLED
    gross_status: GrossStatus = (
        "no_tax_year_row" if tax_year is None else _classify_gross(
            card_gross=card_gross,
            ledger_gross=ledger_gross,
            turnover_at_accept=rollups["turnover_at_accept_inr"],
        )
    )
    tax_status = _classify_tax(
        card_tds=card_tds,
        ledger_tds=ledger_tds,
        tds_at_accept=rollups["tds_at_accept_inr"],
        findings=findings,
        accrual_enabled=accrual_on,
    )

    action_required = tax_status in ("manual", "fixable") or gross_status == "investigate"
    tax_green = tax_status == "match"
    gross_informational_only = gross_status == "expected_v3"

    return {
        "pujari_id": pujari_id,
        "fy_start": anchor.isoformat(),
        "fy_end_exclusive": fy_end.isoformat(),
        "accrual_enabled": accrual_on,
        "tax": {
            "card_tds_accrued_inr": card_tds,
            "ledger_tds_net_inr": ledger_tds,
            "drift_inr": tax_drift,
            "tds_at_accept_from_bookings_inr": rollups["tds_at_accept_inr"],
            "tds_on_collected_with_ledger_inr": rollups["tds_on_collected_with_ledger_inr"],
            "status": tax_status,
            "green": tax_green,
        },
        "gross": {
            "card_gross_facilitation_inr": card_gross,
            "ledger_taxable_base_net_inr": ledger_gross,
            "drift_inr": gross_drift,
            "turnover_at_accept_from_bookings_inr": rollups["turnover_at_accept_inr"],
            "collected_gross_inr": rollups["collected_gross_inr"],
            "status": gross_status,
            "informational_only": gross_informational_only,
        },
        "booking_findings": findings,
        "messages": _messages(
            tax_status=tax_status,
            gross_status=gross_status,
            tax_drift=tax_drift,
            gross_drift=gross_drift,
        ),
        "action_required": action_required,
        "safe_fix_available": tax_status == "fixable" and accrual_on,
    }


async def safe_fix_fy_reconcile(
    db: AsyncSession,
    *,
    pujari_id: uuid.UUID,
    fy_start: dt.date,
    change_reason: str,
) -> dict[str, Any]:
    """Re-queue and process accrual for collected bookings missing ledger — bounded, no card SQL patches."""
    if not get_settings().TDS_ACCRUAL_ENABLED:
        raise HTTPException(
            http.HTTP_409_CONFLICT,
            "TDS accrual disabled — enable TDS_ACCRUAL_ENABLED before safe fix.",
        )

    fy_end = _fy_end(fy_start)
    missing = (
        await db.execute(
            text(
                """
                SELECT b.id, b.total_amount, b.balance_collected_at
                FROM bookings b
                WHERE b.pujari_id = :pid
                  AND b.balance_collected_at >= :fy_start
                  AND b.balance_collected_at < :fy_end
                  AND b.tds_facilitation_fy_applied_at IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM pujari_tds_facilitation_ledger l
                      WHERE l.booking_id = b.id AND l.entry_type = 'accrual'
                  )
                ORDER BY b.balance_collected_at
                LIMIT :lim
                """
            ),
            {
                "pid": str(pujari_id),
                "fy_start": fy_start,
                "fy_end": fy_end,
                "lim": _MAX_SAFE_FIX_BOOKINGS,
            },
        )
    ).mappings().all()

    requeued: list[str] = []
    skipped: list[dict[str, str]] = []

    reconcile_stats = await reconcile_failed_accrual_intents(db, limit=_MAX_SAFE_FIX_BOOKINGS * 4)

    intents_ok = await _intents_table_exists(db)
    for row in missing:
        bid = uuid.UUID(str(row["id"]))
        if intents_ok:
            await db.execute(
                text(
                    """
                    DELETE FROM pujari_tds_accrual_intents
                    WHERE booking_id = :bid AND status IN ('failed', 'parked', 'pending')
                    """
                ),
                {"bid": str(bid)},
            )
        payload = await enqueue_tds_accrual_intent(
            db,
            booking_id=bid,
            pujari_id=pujari_id,
            gross_amount=Decimal(str(row["total_amount"])),
            collected_at=row["balance_collected_at"],
        )
        msg = payload.get("message") or ""
        if "parked" in msg.lower():
            skipped.append({"booking_id": str(bid), "reason": msg})
        else:
            requeued.append(str(bid))

    worker_stats = await process_pending_accrual_intents_for_pujari(
        db, pujari_id=pujari_id, intents_limit=_MAX_SAFE_FIX_BOOKINGS
    )

    after = await troubleshoot_fy_reconcile(db, pujari_id=pujari_id, fy_start=fy_start)
    return {
        "change_reason": change_reason,
        "reconciled_intents": reconcile_stats["reconciled"],
        "requeued_booking_ids": requeued,
        "skipped": skipped,
        "worker_stats": worker_stats,
        "troubleshoot_after": after,
    }


async def reconcile_row_still_present(
    db: AsyncSession, *, pujari_id: uuid.UUID, fy_start: dt.date
) -> dict[str, bool]:
    """Whether fy_reconcile would still list this partner for tax and/or gross."""
    data = await fy_reconcile(db)
    fy_s = fy_start.isoformat()
    tax_row = gross_row = False
    pid_s = str(pujari_id)
    for r in data["rows"]:
        if str(r["pujari_id"]) != pid_s:
            continue
        if str(r["fy_start"]) != fy_s:
            continue
        if r.get("kind") == "tds_accrued":
            tax_row = True
        else:
            gross_row = True
    return {"tax_drift_row": tax_row, "gross_drift_row": gross_row}
