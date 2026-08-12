"""Admin refund ops (A-REFUND)."""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import Principal, require_admin
from app.db.engine import get_db_txn
from app.schemas.admin_refunds import (
    AdminRefundListResponse,
    AdminRefundQueueItem,
    RefundOverrideRequest,
    RefundOverrideResponse,
)
from app.schemas.common import decode_cursor, encode_cursor
from app.services.admin_refund import create_refund_override
from app.services.audit import record_admin_action

router = APIRouter(prefix="/admin/refunds", tags=["admin-refunds"])

_VALID_STATUSES = frozenset(
    {"pending", "processing", "succeeded", "failed", "failed_permanent"}
)


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post("/override", response_model=RefundOverrideResponse)
async def refund_override(
    body: RefundOverrideRequest,
    request: Request,
    p: Principal = Depends(require_admin),
    db: AsyncSession = Depends(get_db_txn),
):
    """Insert refunds row reason=admin_override — worker executes Razorpay (A-REFUND)."""
    refund = await create_refund_override(
        db,
        actor=p,
        amount=body.amount,
        payment_id=body.payment_id,
        booking_id=body.booking_id,
    )
    await record_admin_action(
        db,
        actor_user_id=p.user_id,
        action="refund_override",
        entity_type="refund",
        entity_id=str(refund.id),
        after={
            "payment_id": str(refund.payment_id),
            "booking_id": str(refund.booking_id),
            "amount": str(refund.amount),
            "reason": refund.reason,
        },
        change_reason=body.change_reason,
        ip=_client_ip(request),
    )
    return RefundOverrideResponse(
        refund_id=refund.id,
        payment_id=refund.payment_id,
        booking_id=refund.booking_id,
        amount=Decimal(str(refund.amount)),
        status=refund.status,
    )


@router.get("", response_model=AdminRefundListResponse)
async def list_refunds(
    refund_status: str = Query(..., alias="status", description="Refund status filter"),
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=50),
    _p: Principal = Depends(require_admin),
    db: AsyncSession = Depends(get_db_txn),
):
    """List refunds by status — e.g. failed_permanent queue for ops."""
    if refund_status not in _VALID_STATUSES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"status must be one of: {', '.join(sorted(_VALID_STATUSES))}.",
        )

    params: dict = {"status": refund_status, "lim": limit + 1}
    cursor_pred = ""
    if cursor:
        created_str, id_str = decode_cursor(cursor, 2)
        try:
            params["c_created"] = dt.datetime.fromisoformat(created_str)
            params["c_id"] = uuid.UUID(id_str)
        except ValueError:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid cursor.")
        cursor_pred = "AND (r.created_at, r.id) < (:c_created, :c_id) "

    rows = (
        await db.execute(
            text(
                f"""
                SELECT
                    r.id,
                    r.booking_id,
                    r.payment_id,
                    r.amount,
                    r.status,
                    r.reason,
                    r.last_error,
                    r.attempt_count,
                    r.created_at,
                    u.phone AS customer_phone,
                    u.full_name AS customer_name
                FROM refunds r
                JOIN bookings b ON b.id = r.booking_id
                JOIN users u ON u.id = b.user_id
                WHERE r.status = :status
                {cursor_pred}
                ORDER BY r.created_at DESC, r.id DESC
                LIMIT :lim
                """
            ),
            params,
        )
    ).mappings().all()

    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = encode_cursor(last["created_at"].isoformat(), last["id"])

    refunds = [
        AdminRefundQueueItem(
            id=row["id"],
            booking_id=row["booking_id"],
            payment_id=row["payment_id"],
            amount=Decimal(str(row["amount"])),
            status=row["status"],
            reason=row["reason"],
            last_error=row["last_error"],
            attempt_count=row["attempt_count"],
            created_at=row["created_at"],
            customer_phone=row["customer_phone"],
            customer_name=row["customer_name"],
        )
        for row in rows
    ]
    return AdminRefundListResponse(refunds=refunds, next_cursor=next_cursor)
