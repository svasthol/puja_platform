"""Public app config — no auth (§23.2, P-APP-CONFIG)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.schemas.app_config import AppConfigResponse
from app.services.app_config import load_app_config

router = APIRouter(tags=["app-config"])


@router.get("/app-config", response_model=AppConfigResponse)
async def get_app_config(db: AsyncSession = Depends(get_db)):
    """Launch toggles for Flutter clients — rate-limit at edge."""
    return await load_app_config(db)
