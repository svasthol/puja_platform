"""Admin partner directory + pujari_pricing matrix (Sprint 4B — A-PUJARI-PRICING)."""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import Principal, require_admin, require_admin_role
from app.db.engine import get_db, get_db_txn
from app.models.catalog import PujariServiceArea
from app.models.lookups import ServiceArea
from app.schemas.admin_pujaris import (
    AdminPujariListResponse,
    AdminPujariSummary,
    PujariPricingReplaceRequest,
    PujariPricingResponse,
    PujariPricingRow,
    PujariTaxComplianceResponse,
    PujariTaxComplianceUpdate,
)
from app.services.admin_pujari_fy_report import pujari_fy_earnings_report
from app.services.pujari_compliance import update_tax_compliance
from app.schemas.service_area import PujariServiceAreasReplace
from app.schemas.common import decode_cursor, encode_cursor
from app.services.audit import record_admin_action

router = APIRouter(prefix="/admin/pujaris", tags=["admin-pujaris"])

_VALID_VERIFICATION = frozenset({"pending", "verified", "rejected"})


@router.get("/fy-earnings")
async def list_pujari_fy_earnings(
    request: Request,
    fy_start: dt.date | None = Query(None, description="Indian FY start (default: current FY)"),
    limit: int = Query(100, ge=1, le=500),
    min_gross: Decimal | None = Query(None, ge=0),
    _p: Principal = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Ops report — collections + ledger FY gross per pujari."""
    data = await pujari_fy_earnings_report(
        db, fy_start=fy_start, limit=limit, min_gross=min_gross
    )
    await record_admin_action(
        db,
        actor_user_id=_p.user_id,
        action="read",
        entity_type="pujari_fy_earnings",
        entity_id=None,
        after={"fy_start": data["fy_start"], "limit": limit},
        ip=_client_ip(request),
    )
    await db.commit()
    return data


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def _require_pujari(db: AsyncSession, pujari_id: uuid.UUID) -> dict:
    row = (
        await db.execute(
            text(
                """
                SELECT pj.id, u.full_name, u.phone, pj.verification_status
                FROM pujaris pj
                JOIN users u ON u.id = pj.user_id
                WHERE pj.id = :id
                """
            ),
            {"id": str(pujari_id)},
        )
    ).mappings().first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pujari not found.")
    return dict(row)


def _validate_base_price(base_price: Decimal, default_price: Decimal, price_max: Decimal | None) -> None:
    if price_max is not None and base_price > price_max:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"base_price {base_price} exceeds puja price_max {price_max}.",
        )
    if base_price < 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "base_price must be >= 0.")


@router.get("", response_model=AdminPujariListResponse)
async def list_pujaris(
    q: str | None = Query(None, max_length=100, description="Phone or name substring"),
    verification_status: str | None = Query(None),
    service_area_id: int | None = None,
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=50),
    _p: Principal = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Partner directory — search by phone, name, verification, service area."""
    q_text = q.strip() if isinstance(q, str) and q.strip() else None
    v_status = verification_status if isinstance(verification_status, str) else None
    page_limit = limit if isinstance(limit, int) else 20

    if v_status is not None and v_status not in _VALID_VERIFICATION:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "verification_status must be pending, verified, or rejected.",
        )

    params: dict = {"lim": page_limit + 1}
    filters = "WHERE 1=1 "
    if q_text:
        params["q"] = f"%{q_text}%"
        filters += "AND (u.phone ILIKE :q OR u.full_name ILIKE :q) "
    if v_status:
        params["vstatus"] = v_status
        filters += "AND pj.verification_status = :vstatus "
    if service_area_id is not None:
        params["area"] = service_area_id
        filters += (
            "AND EXISTS (SELECT 1 FROM pujari_service_areas psa "
            "WHERE psa.pujari_id = pj.id AND psa.service_area_id = :area) "
        )

    cursor_pred = ""
    if cursor:
        created_str, id_str = decode_cursor(cursor, 2)
        try:
            params["c_created"] = created_str
            params["c_id"] = uuid.UUID(id_str)
        except ValueError:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid cursor.")
        cursor_pred = "AND (pj.created_at, pj.id) < (:c_created::timestamptz, :c_id) "

    rows = (
        await db.execute(
            text(
                """
                SELECT pj.id, u.full_name, u.phone, pj.verification_status,
                       pj.rating_avg, pj.rating_count, pj.years_experience, pj.created_at,
                       (
                         SELECT COUNT(*)::int FROM pujari_pricing pp
                         WHERE pp.pujari_id = pj.id
                       ) AS pricing_count
                FROM pujaris pj
                JOIN users u ON u.id = pj.user_id
                """
                + filters
                + cursor_pred
                + "ORDER BY pj.created_at DESC, pj.id DESC LIMIT :lim"
            ),
            params,
        )
    ).mappings().all()

    next_cursor = None
    page = list(rows)
    if len(page) > page_limit:
        page = page[:page_limit]
        last = page[-1]
        next_cursor = encode_cursor(last["created_at"], last["id"])

    return AdminPujariListResponse(
        pujaris=[AdminPujariSummary(**dict(r)) for r in page],
        next_cursor=next_cursor,
    )


@router.get("/{pujari_id}/pricing", response_model=PujariPricingResponse)
async def get_pujari_pricing(
    pujari_id: uuid.UUID,
    _p: Principal = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Active pujas with optional base_price for this pujari."""
    pujari = await _require_pujari(db, pujari_id)
    rows = (
        await db.execute(
            text(
                """
                SELECT p.id AS puja_id, p.name AS puja_name,
                       COALESCE(p.slug, '') AS puja_slug,
                       p.default_price, p.price_max, pp.base_price
                FROM pujas p
                LEFT JOIN pujari_pricing pp
                  ON pp.puja_id = p.id AND pp.pujari_id = :pid
                WHERE p.is_active
                ORDER BY p.display_order, p.id
                """
            ),
            {"pid": str(pujari_id)},
        )
    ).mappings().all()

    items = [
        PujariPricingRow(
            puja_id=r["puja_id"],
            puja_name=r["puja_name"],
            puja_slug=r["puja_slug"],
            default_price=Decimal(str(r["default_price"])),
            price_max=Decimal(str(r["price_max"])) if r["price_max"] is not None else None,
            base_price=Decimal(str(r["base_price"])) if r["base_price"] is not None else None,
        )
        for r in rows
    ]
    return PujariPricingResponse(
        pujari_id=pujari_id,
        full_name=pujari["full_name"],
        phone=pujari["phone"],
        verification_status=pujari["verification_status"],
        items=items,
    )


@router.put("/{pujari_id}/pricing", response_model=PujariPricingResponse)
async def replace_pujari_pricing(
    pujari_id: uuid.UUID,
    payload: PujariPricingReplaceRequest,
    request: Request,
    p: Principal = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db_txn),
):
    """Replace-all pricing rows for a pujari (upsert per puja_id)."""
    pujari = await _require_pujari(db, pujari_id)

    puja_ids = [item.puja_id for item in payload.items]
    if len(puja_ids) != len(set(puja_ids)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Duplicate puja_id in items.")

    if puja_ids:
        from sqlalchemy import bindparam

        stmt = (
            text(
                "SELECT id, default_price, price_max FROM pujas "
                "WHERE is_active AND id IN :ids"
            ).bindparams(bindparam("ids", expanding=True))
        )
        puja_rows = (
            await db.execute(stmt, {"ids": [str(x) for x in puja_ids]})
        ).mappings().all()
        found = {uuid.UUID(str(r["id"])): r for r in puja_rows}
        missing = set(puja_ids) - set(found)
        if missing:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Unknown or inactive puja: {missing.pop()}",
            )
        for item in payload.items:
            row = found[item.puja_id]
            price_max = (
                Decimal(str(row["price_max"])) if row["price_max"] is not None else None
            )
            _validate_base_price(item.base_price, Decimal(str(row["default_price"])), price_max)

    before_rows = (
        await db.execute(
            text(
                "SELECT puja_id, base_price FROM pujari_pricing WHERE pujari_id = :pid"
            ),
            {"pid": str(pujari_id)},
        )
    ).mappings().all()
    before = {str(r["puja_id"]): str(r["base_price"]) for r in before_rows}

    await db.execute(
        text("DELETE FROM pujari_pricing WHERE pujari_id = :pid"),
        {"pid": str(pujari_id)},
    )
    for item in payload.items:
        await db.execute(
            text(
                "INSERT INTO pujari_pricing (id, pujari_id, puja_id, base_price) "
                "VALUES (:id, :pid, :puja, :price)"
            ),
            {
                "id": str(uuid.uuid4()),
                "pid": str(pujari_id),
                "puja": str(item.puja_id),
                "price": item.base_price,
            },
        )

    after = {str(item.puja_id): str(item.base_price) for item in payload.items}

    await record_admin_action(
        db,
        actor_user_id=p.user_id,
        action="update",
        entity_type="pujari_pricing",
        entity_id=str(pujari_id),
        before={"pujari": pujari["phone"], "prices": before},
        after={"prices": after},
        change_reason=payload.change_reason,
        ip=_client_ip(request),
    )

    return await get_pujari_pricing(pujari_id, _p=p, db=db)


@router.put("/{pujari_id}/service-areas", status_code=status.HTTP_204_NO_CONTENT)
async def replace_pujari_service_areas(
    pujari_id: uuid.UUID,
    payload: PujariServiceAreasReplace,
    request: Request,
    p: Principal = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db_txn),
):
    """Replace-all pujari_service_areas for a partner."""
    await _require_pujari(db, pujari_id)

    if payload.service_area_ids:
        found = (
            await db.execute(
                select(ServiceArea.id).where(
                    ServiceArea.id.in_(payload.service_area_ids),
                    ServiceArea.is_active.is_(True),
                )
            )
        ).scalars().all()
        if len(found) != len(set(payload.service_area_ids)):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "All service_area_ids must reference active service areas.",
            )

    before_rows = (
        await db.execute(
            text(
                "SELECT service_area_id FROM pujari_service_areas WHERE pujari_id = :pid"
            ),
            {"pid": str(pujari_id)},
        )
    ).scalars().all()

    await db.execute(
        delete(PujariServiceArea).where(PujariServiceArea.pujari_id == pujari_id)
    )
    for aid in payload.service_area_ids:
        db.add(PujariServiceArea(pujari_id=pujari_id, service_area_id=aid))
    await db.flush()

    await record_admin_action(
        db,
        actor_user_id=p.user_id,
        action="replace",
        entity_type="pujari_service_areas",
        entity_id=str(pujari_id),
        before={"service_area_ids": list(before_rows)},
        after={"service_area_ids": payload.service_area_ids},
        change_reason=payload.change_reason,
        ip=_client_ip(request),
    )


@router.patch(
    "/{pujari_id}/tax-compliance",
    response_model=PujariTaxComplianceResponse,
)
async def patch_pujari_tax_compliance(
    pujari_id: uuid.UUID,
    payload: PujariTaxComplianceUpdate,
    request: Request,
    p: Principal = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db_txn),
):
    """Set entity_type and PAN hash for TDS accrual (admin until KYC PAN pipeline ships)."""
    await _require_pujari(db, pujari_id)
    before = (
        await db.execute(
            text(
                "SELECT entity_type, pan_hash IS NOT NULL AS pan_on_file "
                "FROM pujaris WHERE id = :pid"
            ),
            {"pid": str(pujari_id)},
        )
    ).mappings().first()
    result = await update_tax_compliance(
        db,
        pujari_id=pujari_id,
        entity_type=payload.entity_type,
        pan=payload.pan,
        clear_pan=payload.clear_pan,
    )
    await record_admin_action(
        db,
        actor_user_id=p.user_id,
        action="update",
        entity_type="pujaris",
        entity_id=str(pujari_id),
        before=dict(before) if before else None,
        after={"entity_type": result["entity_type"], "pan_on_file": result["pan_on_file"]},
        change_reason=payload.change_reason,
        ip=_client_ip(request),
    )
    return PujariTaxComplianceResponse(
        pujari_id=pujari_id,
        entity_type=result["entity_type"],
        pan_on_file=result["pan_on_file"],
    )

