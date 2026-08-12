"""Admin promo CRUD (A-PROMO)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import Principal, require_admin, require_admin_role
from app.db.engine import get_db, get_db_txn
from app.models.engagement import PromoCode
from app.schemas.admin_promos import (
    AdminPromoCreate,
    AdminPromoListResponse,
    AdminPromoOut,
    AdminPromoUpdate,
)
from app.schemas.common import decode_cursor, encode_cursor
from app.services.audit import record_admin_action

router = APIRouter(prefix="/admin/promos", tags=["admin-promos"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def _promo_out(db: AsyncSession, promo: PromoCode) -> AdminPromoOut:
    count_row = (
        await db.execute(
            text("SELECT COUNT(*) FROM promo_redemptions WHERE promo_code_id = :pid"),
            {"pid": str(promo.id)},
        )
    ).scalar_one()
    return AdminPromoOut(
        id=promo.id,
        code=promo.code,
        discount_pct=promo.discount_pct,
        max_uses_per_user=promo.max_uses_per_user,
        valid_from=promo.valid_from,
        valid_until=promo.valid_until,
        is_active=promo.is_active,
        redemption_count=int(count_row),
    )


@router.get("", response_model=AdminPromoListResponse)
async def list_promos(
    is_active: bool | None = None,
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=50),
    _p: Principal = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    q = select(PromoCode)
    if is_active is not None:
        q = q.where(PromoCode.is_active.is_(is_active))
    if cursor:
        created_str, id_str = decode_cursor(cursor, 2)
        try:
            from datetime import datetime

            c_created = datetime.fromisoformat(created_str)
            c_id = uuid.UUID(id_str)
        except ValueError:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid cursor.")
        q = q.where(
            (PromoCode.valid_from < c_created)
            | ((PromoCode.valid_from == c_created) & (PromoCode.id < c_id))
        )
    rows = (
        await db.execute(q.order_by(PromoCode.valid_from.desc(), PromoCode.id.desc()).limit(limit + 1))
    ).scalars().all()

    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = encode_cursor(last.valid_from.isoformat(), last.id)

    promos = [await _promo_out(db, p) for p in rows]
    return AdminPromoListResponse(promos=promos, next_cursor=next_cursor)


@router.post("", response_model=AdminPromoOut, status_code=status.HTTP_201_CREATED)
async def create_promo(
    payload: AdminPromoCreate,
    request: Request,
    p: Principal = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db_txn),
):
    promo = PromoCode(
        id=uuid.uuid4(),
        code=payload.code,
        discount_pct=payload.discount_pct,
        max_uses_per_user=payload.max_uses_per_user,
        valid_from=payload.valid_from,
        valid_until=payload.valid_until,
        is_active=payload.is_active,
    )
    db.add(promo)
    try:
        await db.flush()
    except IntegrityError as exc:
        diag = getattr(getattr(exc, "orig", None), "diag", None)
        cname = getattr(diag, "constraint_name", "") if diag else ""
        if cname in ("promo_codes_code_key", "ck_promo_codes_valid_range"):
            if cname == "ck_promo_codes_valid_range":
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "valid_until must be after valid_from.",
                )
            raise HTTPException(status.HTTP_409_CONFLICT, "Promo code already exists.")
        raise
    await record_admin_action(
        db,
        actor_user_id=p.user_id,
        action="create",
        entity_type="promo_codes",
        entity_id=str(promo.id),
        after={
            "code": promo.code,
            "discount_pct": promo.discount_pct,
            "valid_from": promo.valid_from.isoformat(),
            "valid_until": promo.valid_until.isoformat(),
            "is_active": promo.is_active,
        },
        change_reason=None,
        ip=_client_ip(request),
    )
    return await _promo_out(db, promo)


@router.put("/{promo_id}", response_model=AdminPromoOut)
async def update_promo(
    promo_id: uuid.UUID,
    payload: AdminPromoUpdate,
    request: Request,
    p: Principal = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db_txn),
):
    promo = (
        await db.execute(select(PromoCode).where(PromoCode.id == promo_id))
    ).scalar_one_or_none()
    if promo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Promo code not found.")

    before = {
        "discount_pct": promo.discount_pct,
        "max_uses_per_user": promo.max_uses_per_user,
        "valid_from": promo.valid_from.isoformat(),
        "valid_until": promo.valid_until.isoformat(),
        "is_active": promo.is_active,
    }

    if payload.discount_pct is not None:
        promo.discount_pct = payload.discount_pct
    if payload.max_uses_per_user is not None:
        promo.max_uses_per_user = payload.max_uses_per_user
    if payload.valid_from is not None:
        promo.valid_from = payload.valid_from
    if payload.valid_until is not None:
        promo.valid_until = payload.valid_until
    if payload.is_active is not None:
        promo.is_active = payload.is_active

    if promo.valid_until <= promo.valid_from:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "valid_until must be after valid_from.",
        )

    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "valid_until must be after valid_from.",
        )

    await record_admin_action(
        db,
        actor_user_id=p.user_id,
        action="update",
        entity_type="promo_codes",
        entity_id=str(promo.id),
        before=before,
        after={
            "discount_pct": promo.discount_pct,
            "max_uses_per_user": promo.max_uses_per_user,
            "valid_from": promo.valid_from.isoformat(),
            "valid_until": promo.valid_until.isoformat(),
            "is_active": promo.is_active,
        },
        change_reason=None,
        ip=_client_ip(request),
    )
    return await _promo_out(db, promo)
