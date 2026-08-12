"""Admin relationship manager CRUD (A-RM)."""
from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import Principal, require_admin, require_admin_role
from app.db.engine import get_db, get_db_txn
from app.models.relationship_manager import RelationshipManager
from app.schemas.relationship_manager import (
    DefaultRelationshipManagerResponse,
    DefaultRelationshipManagerUpdate,
    RelationshipManagerCreate,
    RelationshipManagerListResponse,
    RelationshipManagerOut,
    RelationshipManagerUpdate,
)
from app.services.audit import record_admin_action
from app.services.relationship_manager import (
    get_default_rm_id,
    set_default_rm_id,
)

router = APIRouter(prefix="/admin/relationship-managers", tags=["admin-relationship-managers"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def _rm_out(db: AsyncSession, rm: RelationshipManager) -> RelationshipManagerOut:
    default_id = await get_default_rm_id(db)
    return RelationshipManagerOut(
        id=rm.id,
        name=rm.name,
        phone=rm.phone,
        city=rm.city,
        is_active=rm.is_active,
        is_default=default_id == rm.id,
    )


async def _require_rm(db: AsyncSession, rm_id: uuid.UUID) -> RelationshipManager:
    rm = (
        await db.execute(
            select(RelationshipManager).where(RelationshipManager.id == rm_id)
        )
    ).scalar_one_or_none()
    if rm is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Relationship manager not found.")
    return rm


@router.get("", response_model=RelationshipManagerListResponse)
async def list_relationship_managers(
    city: str | None = Query(None, max_length=80),
    is_active: bool | None = None,
    _p: Principal = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    q = select(RelationshipManager)
    if city and city.strip():
        q = q.where(RelationshipManager.city == city.strip())
    if is_active is not None:
        q = q.where(RelationshipManager.is_active.is_(is_active))
    rows = (
        await db.execute(q.order_by(RelationshipManager.name))
    ).scalars().all()
    items = [await _rm_out(db, rm) for rm in rows]
    return RelationshipManagerListResponse(items=items, next_cursor=None)


@router.get("/default", response_model=DefaultRelationshipManagerResponse)
async def get_default_relationship_manager(
    _p: Principal = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    default_id = await get_default_rm_id(db)
    if default_id is None:
        return DefaultRelationshipManagerResponse(relationship_manager_id=None)
    rm = await _require_rm(db, default_id)
    return DefaultRelationshipManagerResponse(
        relationship_manager_id=rm.id,
        name=rm.name,
        phone=rm.phone,
    )


@router.put("/default", response_model=DefaultRelationshipManagerResponse)
async def set_default_relationship_manager(
    payload: DefaultRelationshipManagerUpdate,
    request: Request,
    p: Principal = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db_txn),
):
    before_id = await get_default_rm_id(db)
    if payload.relationship_manager_id is not None:
        rm = await _require_rm(db, payload.relationship_manager_id)
        if not rm.is_active:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Default RM must be an active relationship manager.",
            )
        await set_default_rm_id(db, rm.id)
        after_id = rm.id
        after_name, after_phone = rm.name, rm.phone
    else:
        await set_default_rm_id(db, None)
        after_id = None
        after_name, after_phone = None, None

    await record_admin_action(
        db,
        actor_user_id=p.user_id,
        action="update",
        entity_type="platform_settings",
        entity_id="default_relationship_manager_id",
        before={"relationship_manager_id": str(before_id) if before_id else None},
        after={"relationship_manager_id": str(after_id) if after_id else None},
        change_reason=payload.change_reason,
        ip=_client_ip(request),
    )
    return DefaultRelationshipManagerResponse(
        relationship_manager_id=after_id,
        name=after_name,
        phone=after_phone,
    )


@router.post("", response_model=RelationshipManagerOut, status_code=status.HTTP_201_CREATED)
async def create_relationship_manager(
    payload: RelationshipManagerCreate,
    request: Request,
    p: Principal = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db_txn),
):
    now = dt.datetime.now(dt.UTC)
    rm = RelationshipManager(
        id=uuid.uuid4(),
        name=payload.name,
        phone=payload.phone,
        city=payload.city,
        is_active=payload.is_active,
        created_at=now,
        updated_at=now,
    )
    db.add(rm)
    await db.flush()

    if payload.set_as_default and rm.is_active:
        await set_default_rm_id(db, rm.id)

    await record_admin_action(
        db,
        actor_user_id=p.user_id,
        action="create",
        entity_type="relationship_managers",
        entity_id=str(rm.id),
        after={
            "name": rm.name,
            "phone": rm.phone,
            "city": rm.city,
            "is_active": rm.is_active,
            "set_as_default": payload.set_as_default,
        },
        change_reason=None,
        ip=_client_ip(request),
    )
    return await _rm_out(db, rm)


@router.put("/{rm_id}", response_model=RelationshipManagerOut)
async def update_relationship_manager(
    rm_id: uuid.UUID,
    payload: RelationshipManagerUpdate,
    request: Request,
    p: Principal = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db_txn),
):
    rm = await _require_rm(db, rm_id)
    before = {
        "name": rm.name,
        "phone": rm.phone,
        "city": rm.city,
        "is_active": rm.is_active,
    }
    changes = payload.model_dump(exclude_unset=True, exclude={"set_as_default", "change_reason"})

    if changes.get("is_active") is False:
        default_id = await get_default_rm_id(db)
        if default_id == rm.id:
            await set_default_rm_id(db, None)

    for field, value in changes.items():
        setattr(rm, field, value)
    rm.updated_at = dt.datetime.now(dt.UTC)
    await db.flush()

    if payload.set_as_default is True:
        if not rm.is_active:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Cannot set inactive RM as default.",
            )
        await set_default_rm_id(db, rm.id)
    elif payload.set_as_default is False:
        default_id = await get_default_rm_id(db)
        if default_id == rm.id:
            await set_default_rm_id(db, None)

    await record_admin_action(
        db,
        actor_user_id=p.user_id,
        action="update",
        entity_type="relationship_managers",
        entity_id=str(rm.id),
        before=before,
        after={
            "name": rm.name,
            "phone": rm.phone,
            "city": rm.city,
            "is_active": rm.is_active,
        },
        change_reason=payload.change_reason,
        ip=_client_ip(request),
    )
    return await _rm_out(db, rm)
