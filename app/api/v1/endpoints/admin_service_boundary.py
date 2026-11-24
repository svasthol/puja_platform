"""Admin launch service boundary (§21.13, A-SERVICE-BOUNDARY)."""
from __future__ import annotations

import datetime as dt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from fastapi.responses import ORJSONResponse

from app.core.config import get_settings
from app.core.dependencies import Principal, require_admin, require_admin_role
from app.db.engine import get_db, get_db_txn
from app.schemas.admin_service_boundary import (
    ServiceBoundaryProbeResponse,
    ServiceBoundarySettingsResponse,
    ServiceBoundarySettingsUpdate,
    ServiceBoundaryStatusResponse,
)
from app.schemas.serviceability import ServiceabilityProbeRequest
from app.services.audit import record_admin_action
from app.services.service_boundary import (
    boundary_outline_geojson,
    boundary_status_dict,
    check_serviceable,
    init_boundary,
    reload_boundary,
    resolve_geojson_path,
)
from app.services.service_boundary_settings import (
    AUDIT_ENTITY_ID,
    load_service_boundary_enabled,
    persist_service_boundary_enabled,
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/admin/settings", tags=["admin-service-boundary"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _ts(dt_val: dt.datetime | None) -> str | None:
    return dt_val.isoformat() if dt_val else None


@router.get("/service-boundary", response_model=ServiceBoundarySettingsResponse)
async def get_service_boundary_settings(
    db: AsyncSession = Depends(get_db),
    _p: Principal = Depends(require_admin),
) -> ServiceBoundarySettingsResponse:
    enabled = await load_service_boundary_enabled(db)
    row = (
        await db.execute(
            text("SELECT updated_at FROM platform_settings WHERE key = 'service_boundary_enabled'")
        )
    ).scalar_one_or_none()
    return ServiceBoundarySettingsResponse(
        service_boundary_enabled=enabled,
        updated_at=_ts(row),
    )


@router.put("/service-boundary", response_model=ServiceBoundarySettingsResponse)
async def update_service_boundary_settings(
    payload: ServiceBoundarySettingsUpdate,
    request: Request,
    p: Principal = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db_txn),
) -> ServiceBoundarySettingsResponse:
    if payload.service_boundary_enabled:
        st = boundary_status_dict()
        if not st["loaded"]:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Cannot enable: service boundary polygon is not loaded.",
            )
    before, _ = await persist_service_boundary_enabled(db, payload.service_boundary_enabled)
    updated_at = (
        await db.execute(
            text("SELECT updated_at FROM platform_settings WHERE key = 'service_boundary_enabled'")
        )
    ).scalar_one_or_none()
    await record_admin_action(
        db,
        actor_user_id=p.user_id,
        action="update",
        entity_type="platform_settings",
        entity_id=AUDIT_ENTITY_ID,
        before={"service_boundary_enabled": before},
        after={"service_boundary_enabled": payload.service_boundary_enabled},
        change_reason=payload.change_reason,
        ip=_client_ip(request),
    )
    return ServiceBoundarySettingsResponse(
        service_boundary_enabled=payload.service_boundary_enabled,
        updated_at=_ts(updated_at),
    )


@router.get("/service-boundary/status", response_model=ServiceBoundaryStatusResponse)
async def service_boundary_status(
    db: AsyncSession = Depends(get_db),
    _p: Principal = Depends(require_admin),
) -> ServiceBoundaryStatusResponse:
    st = boundary_status_dict()
    enabled = await load_service_boundary_enabled(db)
    return ServiceBoundaryStatusResponse(
        service_boundary_enabled=enabled,
        **{k: st[k] for k in ("loaded", "etag", "version", "vertex_count", "bbox", "source_path", "load_error")},
    )


@router.post("/service-boundary/probe", response_model=ServiceBoundaryProbeResponse)
async def service_boundary_probe(
    payload: ServiceabilityProbeRequest,
    _p: Principal = Depends(require_admin),
) -> ServiceBoundaryProbeResponse:
    ok, code = check_serviceable(payload.lat, payload.lng)
    return ServiceBoundaryProbeResponse(serviceable=ok, code=code)


@router.post("/service-boundary/reload", response_model=ServiceBoundaryStatusResponse)
async def service_boundary_reload(
    request: Request,
    p: Principal = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db_txn),
) -> ServiceBoundaryStatusResponse:
    settings = get_settings()
    path = resolve_geojson_path(settings.SERVICE_BOUNDARY_GEOJSON_PATH)
    try:
        reload_boundary(path)
    except (OSError, ValueError, FileNotFoundError) as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Reload failed: {exc}",
        ) from exc
    st = boundary_status_dict()
    await record_admin_action(
        db,
        actor_user_id=p.user_id,
        action="reload",
        entity_type="platform_settings",
        entity_id=AUDIT_ENTITY_ID,
        before=None,
        after={"etag": st.get("etag"), "version": st.get("version")},
        change_reason="service boundary polygon reload",
        ip=_client_ip(request),
    )
    enabled = await load_service_boundary_enabled(db)
    return ServiceBoundaryStatusResponse(
        service_boundary_enabled=enabled,
        **{k: st[k] for k in ("loaded", "etag", "version", "vertex_count", "bbox", "source_path", "load_error")},
    )


@router.get("/service-boundary/geojson")
async def download_service_boundary_geojson(
    _p: Principal = Depends(require_admin),
) -> ORJSONResponse:
    return ORJSONResponse(content=boundary_outline_geojson())