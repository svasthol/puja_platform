"""FCM device token registration (B-DEVICE, API_CONTRACTS POST /v1/me/devices)."""
from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException, status as http
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import Principal, require_customer_or_pujari
from app.db.engine import get_db_txn
from app.schemas.device import DeviceOut, DeviceRegister

router = APIRouter(prefix="/me", tags=["devices"])


@router.post("/devices", response_model=DeviceOut, status_code=http.HTTP_201_CREATED)
async def register_device(
    payload: DeviceRegister,
    p: Principal = Depends(require_customer_or_pujari),
    db: AsyncSession = Depends(get_db_txn),
):
    """Upsert by device_token (globally unique). Re-register moves token to current user."""
    now = dt.datetime.now(dt.UTC)
    device_id = uuid.uuid4()
    row = (
        await db.execute(
            text(
                """
                INSERT INTO devices (id, user_id, device_token, platform, last_seen_at, created_at)
                VALUES (:id, :uid, :tok, :plat, :now, :now)
                ON CONFLICT (device_token) DO UPDATE
                SET user_id = EXCLUDED.user_id,
                    platform = COALESCE(EXCLUDED.platform, devices.platform),
                    last_seen_at = EXCLUDED.last_seen_at
                RETURNING id, device_token, platform, last_seen_at
                """
            ),
            {
                "id": str(device_id),
                "uid": str(p.user_id),
                "tok": payload.device_token,
                "plat": payload.platform,
                "now": now,
            },
        )
    ).mappings().first()
    if row is None:
        raise HTTPException(http.HTTP_500_INTERNAL_SERVER_ERROR, "Device registration failed.")
    return DeviceOut(**dict(row))


@router.delete("/devices/{device_token}", status_code=http.HTTP_204_NO_CONTENT)
async def unregister_device(
    device_token: str,
    p: Principal = Depends(require_customer_or_pujari),
    db: AsyncSession = Depends(get_db_txn),
):
    result = await db.execute(
        text("DELETE FROM devices WHERE device_token = :tok AND user_id = :uid"),
        {"tok": device_token, "uid": str(p.user_id)},
    )
    if result.rowcount == 0:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "Device not found.")
