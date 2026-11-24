"""Customer service area probe + boundary outline (§21.13)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import ORJSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.schemas.serviceability import ServiceabilityResponse
from app.services.service_boundary import (
    boundary_etag,
    boundary_outline_geojson,
    check_serviceable,
)
from app.services.service_boundary_settings import load_service_boundary_enabled

router = APIRouter(tags=["serviceability"])


@router.get("/serviceability", response_model=ServiceabilityResponse)
async def probe_serviceability(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    db: AsyncSession = Depends(get_db),
) -> ServiceabilityResponse:
    if not await load_service_boundary_enabled(db):
        return ServiceabilityResponse(serviceable=True, code=None)
    ok, code = check_serviceable(lat, lng)
    return ServiceabilityResponse(serviceable=ok, code=code)


@router.get("/serviceability/boundary")
async def get_service_boundary_outline(response: Response) -> ORJSONResponse:
    etag = boundary_etag()
    if etag:
        response.headers["ETag"] = f'"{etag}"'
        response.headers["Cache-Control"] = "public, max-age=86400"
    body = boundary_outline_geojson()
    return ORJSONResponse(content=body)