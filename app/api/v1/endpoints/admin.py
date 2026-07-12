"""Admin panel endpoints (role=admin/support). Every action audited."""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import Principal, require_admin
from app.db.engine import get_db, get_db_txn
from app.schemas.admin import AdvanceAmountResponse, AdvanceAmountUpdate

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/settings/advance-booking-amount", response_model=AdvanceAmountResponse)
async def get_advance(_p: Principal = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (
        await db.execute(
            text(
                "SELECT value_json, updated_at FROM platform_settings "
                "WHERE key='advance_booking_amount'"
            )
        )
    ).mappings().first()
    return AdvanceAmountResponse(
        amount=Decimal(str(row["value_json"]["amount"])),
        currency=row["value_json"].get("currency", "INR"),
        updated_at=str(row["updated_at"]),
    )


@router.put("/settings/advance-booking-amount", response_model=AdvanceAmountResponse)
async def set_advance(
    payload: AdvanceAmountUpdate,
    _p: Principal = Depends(require_admin),
    db: AsyncSession = Depends(get_db_txn),
):
    await db.execute(
        text(
            "UPDATE platform_settings SET "
            "value_json = jsonb_build_object('amount', :amt::numeric, 'currency', 'INR'), "
            "updated_at = now() WHERE key='advance_booking_amount'"
        ),
        {"amt": str(payload.amount)},
    )
    return AdvanceAmountResponse(amount=payload.amount, currency="INR")
