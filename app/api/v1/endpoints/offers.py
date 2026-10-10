"""Pujari offer endpoints — accept (the race), reject, list."""
from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import Principal, require_pujari
from app.db.engine import get_db, get_db_txn
from app.schemas.offers import OfferCard, OfferListResponse
from app.services import offer_service
from app.services.booking_gate import compute_lead_hours
from app.services.dispatch_launch import load_dispatch_settings_async

router = APIRouter(tags=["offers"])


@router.get("/offers", response_model=OfferListResponse)
async def list_offers(
    limit: int = Query(50, ge=1, le=50),
    p: Principal = Depends(require_pujari),
    db: AsyncSession = Depends(get_db),
):
    """Live offers — area label only; no customer address or phone (§21.4)."""
    settings = await load_dispatch_settings_async(db)
    rows = (
        await db.execute(
            text(
                """
                SELECT
                    ba.id AS assignment_id,
                    ba.booking_id,
                    ba.expires_at,
                    pu.name AS puja_name,
                    b.scheduled_date,
                    b.scheduled_time,
                    sa.zone_name AS area_label,
                    b.payment_mode,
                    b.total_amount,
                    b.amount_due_offline,
                    b.booking_class,
                    bds.urgency_escalated_at IS NOT NULL AS urgency_escalated
                FROM booking_assignments ba
                JOIN status_types ast ON ast.id = ba.status_id
                  AND ast.domain = 'assignment' AND ast.code = 'offered'
                JOIN pujaris pj ON pj.id = ba.pujari_id
                JOIN bookings b ON b.id = ba.booking_id
                JOIN pujas pu ON pu.id = b.puja_id
                JOIN addresses a ON a.id = b.address_id
                LEFT JOIN service_areas sa ON sa.id = a.service_area_id
                LEFT JOIN booking_dispatch_state bds ON bds.booking_id = b.id
                WHERE pj.user_id = :uid
                  AND b.cancelled_at IS NULL
                  AND ba.responded_at IS NULL
                  AND ba.expires_at > now()
                ORDER BY ba.offered_at DESC
                LIMIT :lim
                """
            ),
            {"uid": str(p.user_id), "lim": limit},
        )
    ).mappings().all()
    offers = []
    for row in rows:
        lead_hours = compute_lead_hours(row["scheduled_date"], row["scheduled_time"])
        urgency = (
            "instant"
            if lead_hours <= settings.instant_lead_hours
            else "advance"
        )
        offers.append(
            OfferCard(
                assignment_id=row["assignment_id"],
                booking_id=row["booking_id"],
                expires_at=row["expires_at"],
                puja_name=row["puja_name"],
                scheduled_date=row["scheduled_date"],
                scheduled_time=row["scheduled_time"],
                area_label=row["area_label"],
                payment_mode=row["payment_mode"],
                total_amount=Decimal(str(row["total_amount"])),
                amount_due_offline=Decimal(str(row["amount_due_offline"])),
                booking_class=row["booking_class"] or "advance",
                urgency=urgency,
                urgency_escalated=bool(row["urgency_escalated"]),
            )
        )
    return OfferListResponse(offers=offers, next_cursor=None)


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
