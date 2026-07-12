"""Customer address CRUD (C-ADDR, API_CONTRACTS §Addresses v3.2).

geom is derived by DB trigger trg_addresses_geom_sync (migration 005) on every
lat/lng write — this module never touches PostGIS directly. Checkout rejects
addresses with geom IS NULL (422), so lat/lng are mandatory on create.
"""
from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status as http
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import Principal, require_customer
from app.db.engine import get_db, get_db_txn
from app.models.identity import Address
from app.schemas.address import AddressCreate, AddressOut, AddressPage, AddressUpdate
from app.schemas.common import decode_cursor, encode_cursor

router = APIRouter(prefix="/addresses", tags=["addresses"])


def _out(a: Address) -> AddressOut:
    return AddressOut(
        id=a.id,
        line1=a.line1,
        line2=a.line2,
        city=a.city,
        state=a.state,
        pincode=a.pincode,
        latitude=a.latitude,
        longitude=a.longitude,
        is_default=a.is_default,
        created_at=a.created_at,
    )


async def _clear_default(db: AsyncSession, user_id: uuid.UUID) -> None:
    # ux_addresses_one_default_per_user allows only one default row
    await db.execute(
        update(Address).where(Address.user_id == user_id, Address.is_default.is_(True))
        .values(is_default=False)
    )


@router.get("", response_model=AddressPage)
async def list_addresses(
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=50),
    p: Principal = Depends(require_customer),
    db: AsyncSession = Depends(get_db),
):
    q = select(Address).where(Address.user_id == p.user_id)
    if cursor:
        created_str, id_str = decode_cursor(cursor, 2)
        try:
            after_dt = dt.datetime.fromisoformat(created_str)
            after_id = uuid.UUID(id_str)
        except ValueError:
            raise HTTPException(http.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid cursor.")
        q = q.where(
            text("(created_at, id) < (:c_dt, :c_id)").bindparams(c_dt=after_dt, c_id=after_id)
        )
    rows = (
        await db.execute(q.order_by(Address.created_at.desc(), Address.id.desc()).limit(limit + 1))
    ).scalars().all()
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = encode_cursor(last.created_at.isoformat(), last.id)
    return AddressPage(addresses=[_out(a) for a in rows], next_cursor=next_cursor)


@router.post("", response_model=AddressOut, status_code=http.HTTP_201_CREATED)
async def create_address(
    payload: AddressCreate,
    p: Principal = Depends(require_customer),
    db: AsyncSession = Depends(get_db_txn),
):
    if payload.is_default:
        await _clear_default(db, p.user_id)
    addr = Address(
        id=uuid.uuid4(),
        user_id=p.user_id,
        line1=payload.line1,
        line2=payload.line2,
        city=payload.city,
        state=payload.state,
        pincode=payload.pincode,
        latitude=payload.latitude,
        longitude=payload.longitude,
        is_default=payload.is_default,
        created_at=dt.datetime.now(dt.UTC),
    )
    db.add(addr)
    await db.flush()
    return _out(addr)


@router.put("/{address_id}", response_model=AddressOut)
async def update_address(
    address_id: uuid.UUID,
    payload: AddressUpdate,
    p: Principal = Depends(require_customer),
    db: AsyncSession = Depends(get_db_txn),
):
    addr = (
        await db.execute(
            select(Address).where(Address.id == address_id).with_for_update()
        )
    ).scalar_one_or_none()
    if addr is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "Address not found.")
    if addr.user_id != p.user_id:
        raise HTTPException(http.HTTP_403_FORBIDDEN, "Not your address.")

    changes = payload.model_dump(exclude_unset=True)
    if changes.get("is_default") is True and not addr.is_default:
        await _clear_default(db, p.user_id)
    for field, value in changes.items():
        setattr(addr, field, value)
    await db.flush()  # trigger recomputes geom when lat/lng changed
    return _out(addr)
