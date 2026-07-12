"""Pujari self-service: heartbeat/presence, availability, service lifecycle."""
from __future__ import annotations

import datetime as dt
import uuid
import zoneinfo

from fastapi import APIRouter, Depends, HTTPException, status as http
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.dependencies import Principal, require_pujari
from app.core.redis_client import redis_delete, redis_set
from app.db.engine import get_db, get_db_txn
from app.schemas.booking import BalanceCollected

router = APIRouter(prefix="/me", tags=["pujari-self"])
settings = get_settings()
_TZ = zoneinfo.ZoneInfo(settings.PLATFORM_TIMEZONE)


class Heartbeat(BaseModel):
    lat: float
    lng: float


async def _pujari_id(db: AsyncSession, user_id: uuid.UUID) -> uuid.UUID:
    pid = (
        await db.execute(text("SELECT id FROM pujaris WHERE user_id = :uid"), {"uid": str(user_id)})
    ).scalar_one_or_none()
    if pid is None:
        raise HTTPException(http.HTTP_403_FORBIDDEN, "Not a pujari account.")
    return pid


@router.put("/heartbeat")
async def heartbeat(
    body: Heartbeat, p: Principal = Depends(require_pujari), db: AsyncSession = Depends(get_db_txn)
):
    pid = await _pujari_id(db, p.user_id)
    # write live location + geom, then presence key with TTL
    await db.execute(
        text(
            "INSERT INTO pujari_live_location (pujari_id, latitude, longitude, geom, updated_at) "
            "VALUES (:pid, :lat, :lng, ST_SetSRID(ST_MakePoint(:lng, :lat),4326)::geography, now()) "
            "ON CONFLICT (pujari_id) DO UPDATE SET latitude=:lat, longitude=:lng, "
            "geom=ST_SetSRID(ST_MakePoint(:lng, :lat),4326)::geography, updated_at=now()"
        ),
        {"pid": str(pid), "lat": body.lat, "lng": body.lng},
    )
    await redis_set(f"presence:{pid}", "1", ex=settings.PUJARI_PRESENCE_TTL_SECONDS)
    return {"status": "ok"}


@router.delete("/heartbeat")
async def go_offline(p: Principal = Depends(require_pujari), db: AsyncSession = Depends(get_db_txn)):
    pid = await _pujari_id(db, p.user_id)
    await redis_delete(f"presence:{pid}")
    return {"status": "offline"}


# ---- B-AVAIL / B-UNAVAIL (API_CONTRACTS PUT /v1/me/availability|unavailability)


class AvailabilityWindow(BaseModel):
    day_of_week: int = Field(ge=0, le=6)  # 0=Mon..6=Sun, matches schema CHECK
    start_time: dt.time
    end_time: dt.time

    @model_validator(mode="after")
    def _end_after_start(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class AvailabilityPut(BaseModel):
    windows: list[AvailabilityWindow] = Field(max_length=50)


class UnavailableDate(BaseModel):
    date: dt.date
    reason: str | None = Field(default=None, max_length=100)


class UnavailabilityPut(BaseModel):
    dates: list[UnavailableDate] = Field(max_length=100)


@router.get("/availability")
async def get_availability(
    p: Principal = Depends(require_pujari), db: AsyncSession = Depends(get_db)
):
    pid = await _pujari_id(db, p.user_id)
    rows = (
        await db.execute(
            text(
                "SELECT day_of_week, start_time, end_time FROM pujari_availability "
                "WHERE pujari_id = :pid ORDER BY day_of_week, start_time"
            ),
            {"pid": str(pid)},
        )
    ).mappings().all()
    return {"windows": [dict(r) for r in rows]}


@router.put("/availability")
async def put_availability(
    payload: AvailabilityPut,
    p: Principal = Depends(require_pujari),
    db: AsyncSession = Depends(get_db_txn),
):
    """Replace-all weekly windows. Dispatch/catalog read these live."""
    pid = await _pujari_id(db, p.user_id)
    seen = {(w.day_of_week, w.start_time) for w in payload.windows}
    if len(seen) != len(payload.windows):
        raise HTTPException(
            http.HTTP_422_UNPROCESSABLE_ENTITY, "Duplicate (day_of_week, start_time) window."
        )
    await db.execute(
        text("DELETE FROM pujari_availability WHERE pujari_id = :pid"), {"pid": str(pid)}
    )
    for w in payload.windows:
        await db.execute(
            text(
                "INSERT INTO pujari_availability (id, pujari_id, day_of_week, start_time, end_time) "
                "VALUES (:id, :pid, :dow, :st, :et)"
            ),
            {
                "id": str(uuid.uuid4()),
                "pid": str(pid),
                "dow": w.day_of_week,
                "st": w.start_time,
                "et": w.end_time,
            },
        )
    return {"status": "ok", "windows": len(payload.windows)}


@router.get("/unavailability")
async def get_unavailability(
    p: Principal = Depends(require_pujari), db: AsyncSession = Depends(get_db)
):
    pid = await _pujari_id(db, p.user_id)
    rows = (
        await db.execute(
            text(
                "SELECT unavailable_date, reason FROM pujari_unavailability "
                "WHERE pujari_id = :pid ORDER BY unavailable_date"
            ),
            {"pid": str(pid)},
        )
    ).mappings().all()
    return {"dates": [dict(r) for r in rows]}


@router.put("/unavailability")
async def put_unavailability(
    payload: UnavailabilityPut,
    p: Principal = Depends(require_pujari),
    db: AsyncSession = Depends(get_db_txn),
):
    """Replace-all date blocks. Dispatch and catalog exclude these dates."""
    pid = await _pujari_id(db, p.user_id)
    if len({d.date for d in payload.dates}) != len(payload.dates):
        raise HTTPException(http.HTTP_422_UNPROCESSABLE_ENTITY, "Duplicate date.")
    await db.execute(
        text("DELETE FROM pujari_unavailability WHERE pujari_id = :pid"), {"pid": str(pid)}
    )
    for d in payload.dates:
        await db.execute(
            text(
                "INSERT INTO pujari_unavailability (id, pujari_id, unavailable_date, reason) "
                "VALUES (:id, :pid, :d, :r)"
            ),
            {"id": str(uuid.uuid4()), "pid": str(pid), "d": d.date, "r": d.reason},
        )
    return {"status": "ok", "dates": len(payload.dates)}
