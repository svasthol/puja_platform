"""Admin service areas CRUD + pujari zone assignment (A-AREAS)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import Principal, require_admin, require_admin_role
from app.db.engine import get_db, get_db_txn
from app.models.lookups import ServiceArea
from app.schemas.service_area import (
    ServiceAreaCreate,
    ServiceAreaListResponse,
    ServiceAreaOut,
    ServiceAreaUpdate,
)
from app.services.audit import record_admin_action
from app.services.service_area_guard import (
    count_active_bookings_for_area,
    count_pujaris_in_area,
)

router = APIRouter(prefix="/admin/service-areas", tags=["admin-service-areas"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def _area_out(db: AsyncSession, area: ServiceArea) -> ServiceAreaOut:
    pujari_count = await count_pujaris_in_area(db, area.id)
    active_booking_count = await count_active_bookings_for_area(db, area.id)
    return ServiceAreaOut(
        id=area.id,
        city=area.city,
        zone_name=area.zone_name,
        pincode=area.pincode,
        is_active=area.is_active,
        pujari_count=pujari_count,
        active_booking_count=active_booking_count,
    )


async def _require_area(db: AsyncSession, area_id: int) -> ServiceArea:
    area = (
        await db.execute(select(ServiceArea).where(ServiceArea.id == area_id))
    ).scalar_one_or_none()
    if area is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Service area not found.")
    return area


@router.get("", response_model=ServiceAreaListResponse)
async def list_service_areas(
    city: str | None = Query(None, max_length=80),
    is_active: bool | None = None,
    _p: Principal = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    q = select(ServiceArea)
    if city and city.strip():
        q = q.where(ServiceArea.city == city.strip())
    if is_active is not None:
        q = q.where(ServiceArea.is_active.is_(is_active))
    rows = (
        await db.execute(q.order_by(ServiceArea.city, ServiceArea.zone_name))
    ).scalars().all()
    return ServiceAreaListResponse(
        areas=[await _area_out(db, a) for a in rows],
        next_cursor=None,
    )


@router.post("", response_model=ServiceAreaOut, status_code=status.HTTP_201_CREATED)
async def create_service_area(
    payload: ServiceAreaCreate,
    request: Request,
    p: Principal = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db_txn),
):
    area = ServiceArea(
        city=payload.city,
        zone_name=payload.zone_name,
        pincode=payload.pincode,
        is_active=payload.is_active,
    )
    db.add(area)
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "A service area with this city and zone name already exists.",
        )
    await record_admin_action(
        db,
        actor_user_id=p.user_id,
        action="create",
        entity_type="service_areas",
        entity_id=str(area.id),
        after={
            "city": area.city,
            "zone_name": area.zone_name,
            "pincode": area.pincode,
            "is_active": area.is_active,
        },
        change_reason=None,
        ip=_client_ip(request),
    )
    return await _area_out(db, area)


@router.put("/{area_id}", response_model=ServiceAreaOut)
async def update_service_area(
    area_id: int,
    payload: ServiceAreaUpdate,
    request: Request,
    p: Principal = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db_txn),
):
    area = await _require_area(db, area_id)
    before = {
        "city": area.city,
        "zone_name": area.zone_name,
        "pincode": area.pincode,
        "is_active": area.is_active,
    }
    changes = payload.model_dump(exclude_unset=True, exclude={"force_deactivate", "change_reason"})

    if changes.get("is_active") is False and area.is_active:
        active_count = await count_active_bookings_for_area(db, area_id)
        if active_count > 0 and not payload.force_deactivate:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail={
                    "message": (
                        "Cannot deactivate: pujaris in this area have active bookings. "
                        "Pass force_deactivate=true to confirm."
                    ),
                    "active_booking_count": active_count,
                },
            )

    for field, value in changes.items():
        setattr(area, field, value)

    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "A service area with this city and zone name already exists.",
        )

    await record_admin_action(
        db,
        actor_user_id=p.user_id,
        action="update",
        entity_type="service_areas",
        entity_id=str(area.id),
        before=before,
        after={
            "city": area.city,
            "zone_name": area.zone_name,
            "pincode": area.pincode,
            "is_active": area.is_active,
        },
        change_reason=payload.change_reason,
        ip=_client_ip(request),
    )
    return await _area_out(db, area)
