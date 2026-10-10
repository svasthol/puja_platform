"""Admin TDS compliance (§0.S — backlog, reconcile, corrections)."""
from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import Principal, require_admin, require_admin_role
from app.db.engine import get_db, get_db_txn
from app.schemas.admin_tds import (
    TdsAccrualIntentRow,
    TdsComplianceBacklogResponse,
    TdsCorrectOfflineCollectionRequest,
    TdsCorrectOfflineCollectionResponse,
    TdsFyReconcileResponse,
    TdsFyTroubleshootFixRequest,
    TdsFyTroubleshootFixResponse,
    TdsFyTroubleshootResponse,
    TdsPujariReadinessRow,
)
from app.services.admin_tds_compliance import (
    compliance_backlog,
    correct_offline_collection,
    fy_reconcile,
)
from app.services.admin_tds_troubleshoot import (
    safe_fix_fy_reconcile,
    troubleshoot_fy_reconcile,
)
from app.services.audit import record_admin_action
from app.services.tds_accrual_service import fy_start_for_date

router = APIRouter(prefix="/admin/tds", tags=["admin-tds"])


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.get("/compliance-backlog", response_model=TdsComplianceBacklogResponse)
async def get_compliance_backlog(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    _p: Principal = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    data = await compliance_backlog(db, limit=limit)
    await record_admin_action(
        db,
        actor_user_id=_p.user_id,
        action="read",
        entity_type="tds_compliance_backlog",
        entity_id=None,
        after={"limit": limit},
        ip=_ip(request),
    )
    await db.commit()
    intents = [
        TdsAccrualIntentRow(
            intent_id=row["intent_id"],
            booking_id=row["booking_id"],
            pujari_id=row["pujari_id"],
            status=row["status"],
            park_reason=row["park_reason"],
            gross_amount=row["gross_amount"],
            collected_at=str(row["collected_at"]),
            snapshot_entity_type=row["snapshot_entity_type"],
            snapshot_pan_on_file=row["snapshot_pan_on_file"],
            attempt_count=row["attempt_count"],
            last_error=row["last_error"],
            created_at=str(row["created_at"]),
        )
        for row in data["intents"]
    ]
    readiness = [
        TdsPujariReadinessRow(
            pujari_id=r["pujari_id"],
            entity_type=r["entity_type"],
            pan_on_file=bool(r["pan_on_file"]),
            pan_status=r["pan_status"],
            parked_intents=int(r["parked_intents"]),
            pending_intents=int(r["pending_intents"]),
        )
        for r in data["pujari_readiness"]
    ]
    return TdsComplianceBacklogResponse(
        parked_count=data["parked_count"],
        pending_count=data["pending_count"],
        failed_count=data["failed_count"],
        intents=intents,
        pujari_readiness=readiness,
    )


@router.get("/fy-reconcile", response_model=TdsFyReconcileResponse)
async def get_fy_reconcile(
    request: Request,
    _p: Principal = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    data = await fy_reconcile(db)
    await record_admin_action(
        db,
        actor_user_id=_p.user_id,
        action="read",
        entity_type="tds_fy_reconcile",
        entity_id=None,
        after={"green": data["green"], "drift_rows": len(data["rows"])},
        ip=_ip(request),
    )
    await db.commit()
    rows = [
        {
            "pujari_id": r["pujari_id"],
            "fy_start": r["fy_start"],
            "kind": r.get("kind", "gross_facilitation"),
            "accumulator_gross": r["accumulator"],
            "ledger_net": r["ledger_net"],
            "drift": r["drift"],
        }
        for r in data["rows"]
    ]
    return TdsFyReconcileResponse(green=data["green"], rows=rows)


@router.get("/fy-reconcile/troubleshoot", response_model=TdsFyTroubleshootResponse)
async def get_fy_reconcile_troubleshoot(
    request: Request,
    pujari_id: uuid.UUID,
    fy_start: dt.date | None = Query(None, description="Indian FY start (default: current FY)"),
    _p: Principal = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    anchor = fy_start or fy_start_for_date(dt.date.today())
    data = await troubleshoot_fy_reconcile(db, pujari_id=pujari_id, fy_start=anchor)
    await record_admin_action(
        db,
        actor_user_id=_p.user_id,
        action="read",
        entity_type="tds_fy_troubleshoot",
        entity_id=str(pujari_id),
        after={"fy_start": anchor.isoformat(), "tax_status": data["tax"]["status"]},
        ip=_ip(request),
    )
    await db.commit()
    return TdsFyTroubleshootResponse.model_validate(data)


@router.post("/fy-reconcile/troubleshoot/fix", response_model=TdsFyTroubleshootFixResponse)
async def post_fy_reconcile_troubleshoot_fix(
    request: Request,
    pujari_id: uuid.UUID,
    payload: TdsFyTroubleshootFixRequest,
    fy_start: dt.date | None = Query(None, description="Indian FY start (default: current FY)"),
    p: Principal = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db_txn),
):
    anchor = fy_start or fy_start_for_date(dt.date.today())
    result = await safe_fix_fy_reconcile(
        db,
        pujari_id=pujari_id,
        fy_start=anchor,
        change_reason=payload.change_reason,
    )
    after = result["troubleshoot_after"]
    await record_admin_action(
        db,
        actor_user_id=p.user_id,
        action="update",
        entity_type="tds_fy_troubleshoot_fix",
        entity_id=str(pujari_id),
        after={
            "fy_start": anchor.isoformat(),
            "requeued": len(result["requeued_booking_ids"]),
            "tax_green_after": after["tax"]["green"],
        },
        change_reason=payload.change_reason,
        ip=_ip(request),
    )
    fix_payload = {**result, "troubleshoot_after": TdsFyTroubleshootResponse.model_validate(after)}
    return TdsFyTroubleshootFixResponse.model_validate(fix_payload)


@router.post(
    "/bookings/{booking_id}/correct-offline-collection",
    response_model=TdsCorrectOfflineCollectionResponse,
)
async def post_correct_offline_collection(
    booking_id: uuid.UUID,
    payload: TdsCorrectOfflineCollectionRequest,
    request: Request,
    p: Principal = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db_txn),
):
    result = await correct_offline_collection(
        db,
        booking_id=booking_id,
        action=payload.action,
        amount=payload.amount,
        change_reason=payload.change_reason,
    )
    await record_admin_action(
        db,
        actor_user_id=p.user_id,
        action="update",
        entity_type="booking_offline_collection",
        entity_id=str(booking_id),
        after={
            "action": payload.action,
            "amount": str(payload.amount) if payload.amount is not None else None,
            "tds_reversal": result.get("tds_reversal"),
            "tds_requeued": result.get("tds_requeued"),
        },
        change_reason=payload.change_reason,
        ip=_ip(request),
    )
    return TdsCorrectOfflineCollectionResponse(
        booking_id=result["booking_id"],
        balance_collected_amount=result.get("balance_collected_amount"),
        balance_collected_at=result.get("balance_collected_at"),
        tds_reversal=result.get("tds_reversal"),
        tds_requeued=bool(result.get("tds_requeued")),
    )
