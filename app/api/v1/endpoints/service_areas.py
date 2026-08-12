"""Customer service areas dropdown (P-LAUNCH-AREA)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import Principal, require_customer
from app.db.engine import get_db
from app.models.lookups import ServiceArea
from app.schemas.service_area import ServiceAreaPublic, ServiceAreaPublicList

router = APIRouter(tags=["service-areas"])


@router.get("/service-areas", response_model=ServiceAreaPublicList)
async def list_active_service_areas(
    city: str | None = Query(None, max_length=80),
    _p: Principal = Depends(require_customer),
    db: AsyncSession = Depends(get_db),
):
    """Active zones for address dropdown (§21.3). Display label only at launch."""
    q = select(ServiceArea).where(ServiceArea.is_active.is_(True))
    if city and city.strip():
        q = q.where(ServiceArea.city == city.strip())
    rows = (
        await db.execute(q.order_by(ServiceArea.city, ServiceArea.zone_name))
    ).scalars().all()
    return ServiceAreaPublicList(
        areas=[
            ServiceAreaPublic(id=a.id, city=a.city, zone_name=a.zone_name) for a in rows
        ]
    )
