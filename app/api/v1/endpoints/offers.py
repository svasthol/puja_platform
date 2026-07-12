"""Pujari offer endpoints — accept (the race), reject, list."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status as http
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import Principal, require_pujari
from app.db.engine import get_db, get_db_txn
from app.services import offer_service

router = APIRouter(tags=["offers"])


@router.get("/offers")
async def list_offers(p: Principal = Depends(require_pujari), db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(
            text(
                "SELECT ba.id AS assignment_id, ba.booking_id, ba.expires_at, "
                "b.payment_mode, b.amount_due_offline, b.scheduled_date, b.scheduled_time "
                "FROM booking_assignments ba "
                "JOIN pujaris pj ON pj.id = ba.pujari_id "
                "JOIN bookings b ON b.id = ba.booking_id "
                "WHERE pj.user_id = :uid AND ba.responded_at IS NULL "
                "ORDER BY ba.offered_at DESC LIMIT 50"
            ),
            {"uid": str(p.user_id)},
        )
    ).mappings().all()
    return {"offers": [dict(r) for r in rows]}


@router.post("/offers/{assignment_id}/accept")
async def accept(
    assignment_id: uuid.UUID,
    p: Principal = Depends(require_pujari),
    db: AsyncSession = Depends(get_db_txn),
):
    return await offer_service.accept_offer(db, user_id=p.user_id, assignment_id=assignment_id)


@router.post("/offers/{assignment_id}/reject")
async def reject(
    assignment_id: uuid.UUID,
    p: Principal = Depends(require_pujari),
    db: AsyncSession = Depends(get_db_txn),
):
    result = await offer_service.reject_offer(db, user_id=p.user_id, assignment_id=assignment_id)
    if result.get("enqueue_rebroadcast"):
        from app.workers.celery_app import celery_app

        celery_app.send_task(
            "app.workers.dispatch.rebroadcast_booking",
            args=[result["enqueue_rebroadcast"]],
        )
    return result
