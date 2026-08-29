"""Admin catalogue CRUD (Sprint 4B Wave 1 — A-CAT-*).

RBAC: read → require_admin; write → require_admin_role (ADMIN.md matrix).
"""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import Principal, require_admin, require_admin_role
from app.db.engine import get_db, get_db_txn
from app.models.catalog import Puja, PujaAddon, PujaContentItem, PujaI18n, PujaMedia
from app.models.lookups import PujaCategory
from app.schemas.catalog_admin import (
    ContentListResponse,
    ContentReplaceRequest,
    PujaAddonCreate,
    PujaAddonListResponse,
    PujaAddonResponse,
    PujaAddonUpdate,
    PujaCategoryCreate,
    PujaCategoryListResponse,
    PujaCategoryResponse,
    PujaCategoryUpdate,
    PujaCreate,
    PujaImpactResponse,
    PujaI18nResponse,
    PujaI18nUpdate,
    PujaListResponse,
    PujaReorderRequest,
    PujaResponse,
    PujaUpdate,
    ReorderRequest,
    MediaListResponse,
    MediaPresignRequest,
    MediaPresignResponse,
    MediaResponse,
)
from app.services.audit import record_admin_action
from app.services.partner_dispatch_readiness import ensure_puja_pricing_for_verified_pujaris
from app.services.catalog_media import (
    CatalogMediaError,
    CatalogStorageNotConfigured,
    build_s3_key,
    head_catalog_object,
    presign_catalog_put,
    public_url,
    put_catalog_object,
    validate_head_for_confirm,
)
from app.services.catalog_slugs import slugify_name, unique_slug

router = APIRouter(prefix="/admin/catalog", tags=["admin-catalog"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _category_response(cat: PujaCategory) -> PujaCategoryResponse:
    return PujaCategoryResponse(
        id=cat.id,
        name=cat.name,
        slug=cat.slug or slugify_name(cat.name),
        description=cat.description,
        display_order=cat.display_order,
        is_active=cat.is_active,
        image_media_id=cat.image_media_id,
    )


def _puja_response(p: Puja) -> PujaResponse:
    return PujaResponse(
        id=p.id,
        category_id=p.category_id,
        name=p.name,
        slug=p.slug or "",
        tagline=p.tagline,
        description=p.description,
        duration_minutes=p.duration_minutes,
        default_price=Decimal(str(p.default_price)),
        price_max=Decimal(str(p.price_max)) if p.price_max is not None else None,
        display_order=p.display_order,
        is_active=p.is_active,
        hero_media_id=p.hero_media_id,
    )


def _addon_response(a: PujaAddon) -> PujaAddonResponse:
    return PujaAddonResponse(
        id=a.id,
        puja_id=a.puja_id,
        name=a.name,
        description=a.description,
        price=Decimal(str(a.price)),
        display_order=a.display_order,
        is_active=a.is_active,
        image_media_id=a.image_media_id,
    )


async def _next_category_order(db: AsyncSession) -> int:
    current = (
        await db.execute(select(func.coalesce(func.max(PujaCategory.display_order), -1)))
    ).scalar_one()
    return int(current) + 1


async def _next_puja_order(db: AsyncSession, category_id: int) -> int:
    current = (
        await db.execute(
            select(func.coalesce(func.max(Puja.display_order), -1)).where(
                Puja.category_id == category_id
            )
        )
    ).scalar_one()
    return int(current) + 1


async def _require_category(db: AsyncSession, category_id: int) -> PujaCategory:
    cat = (
        await db.execute(select(PujaCategory).where(PujaCategory.id == category_id))
    ).scalar_one_or_none()
    if cat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found.")
    return cat


async def _require_puja(db: AsyncSession, puja_id: uuid.UUID) -> Puja:
    puja = (await db.execute(select(Puja).where(Puja.id == puja_id))).scalar_one_or_none()
    if puja is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Puja not found.")
    return puja


def _validate_price_max(default_price: Decimal, price_max: Decimal | None) -> None:
    if price_max is not None and price_max < default_price:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "price_max must be greater than or equal to default_price.",
        )


async def _reject_duplicate_category_name(db: AsyncSession, name: str) -> None:
    exists = (
        await db.execute(select(PujaCategory.id).where(PujaCategory.name == name))
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Category '{name}' already exists.",
        )


# --------------------------------------------------------------------------- #
# Categories
# --------------------------------------------------------------------------- #
@router.get("/categories", response_model=PujaCategoryListResponse)
async def list_categories(
    _p: Principal = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(PujaCategory).order_by(PujaCategory.display_order, PujaCategory.id)
        )
    ).scalars().all()
    return PujaCategoryListResponse(categories=[_category_response(c) for c in rows])


@router.post(
    "/categories",
    response_model=PujaCategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_category(
    payload: PujaCategoryCreate,
    request: Request,
    p: Principal = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db_txn),
):
    await _reject_duplicate_category_name(db, payload.name)
    slug = slugify_name(payload.name)
    cat = PujaCategory(
        name=payload.name,
        slug=slug,
        description=payload.description,
        display_order=await _next_category_order(db),
        is_active=True,
    )
    db.add(cat)
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Category '{payload.name}' already exists.",
        ) from None

    await record_admin_action(
        db,
        actor_user_id=p.user_id,
        action="create",
        entity_type="puja_categories",
        entity_id=str(cat.id),
        after={"name": cat.name, "slug": cat.slug, "is_active": cat.is_active},
        change_reason=payload.change_reason,
        ip=_client_ip(request),
    )
    return _category_response(cat)


@router.put("/categories/{category_id}", response_model=PujaCategoryResponse)
async def update_category(
    category_id: int,
    payload: PujaCategoryUpdate,
    request: Request,
    p: Principal = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db_txn),
):
    if all(
        v is None
        for v in (payload.name, payload.description, payload.is_active, payload.image_media_id)
    ):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No fields to update.")

    cat = await _require_category(db, category_id)
    before = {
        "name": cat.name,
        "description": cat.description,
        "is_active": cat.is_active,
        "image_media_id": str(cat.image_media_id) if cat.image_media_id else None,
    }

    if payload.name is not None:
        cat.name = payload.name
    if payload.description is not None:
        cat.description = payload.description
    if payload.is_active is not None:
        cat.is_active = payload.is_active
    if payload.image_media_id is not None:
        cat.image_media_id = payload.image_media_id

    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Category name '{payload.name}' already exists.",
        ) from None

    await record_admin_action(
        db,
        actor_user_id=p.user_id,
        action="update",
        entity_type="puja_categories",
        entity_id=str(cat.id),
        before=before,
        after={
            "name": cat.name,
            "description": cat.description,
            "is_active": cat.is_active,
            "image_media_id": str(cat.image_media_id) if cat.image_media_id else None,
        },
        change_reason=payload.change_reason,
        ip=_client_ip(request),
    )
    return _category_response(cat)


@router.patch("/categories/reorder", response_model=PujaCategoryListResponse)
async def reorder_categories(
    payload: ReorderRequest,
    request: Request,
    p: Principal = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db_txn),
):
    for position, cat_id in enumerate(payload.ordered_ids):
        result = await db.execute(
            text(
                "UPDATE puja_categories SET display_order = :pos WHERE id = :id"
            ),
            {"pos": position, "id": cat_id},
        )
        if result.rowcount == 0:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Category {cat_id} not found.")

    await record_admin_action(
        db,
        actor_user_id=p.user_id,
        action="reorder",
        entity_type="puja_categories",
        after={"ordered_ids": payload.ordered_ids},
        change_reason=payload.change_reason,
        ip=_client_ip(request),
    )
    return await list_categories(_p=p, db=db)


# --------------------------------------------------------------------------- #
# Pujas
# --------------------------------------------------------------------------- #
@router.get("/pujas", response_model=PujaListResponse)
async def list_pujas(
    category_id: int | None = None,
    _p: Principal = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Puja).order_by(Puja.display_order, Puja.id)
    if category_id is not None:
        stmt = stmt.where(Puja.category_id == category_id)
    rows = (await db.execute(stmt)).scalars().all()
    return PujaListResponse(pujas=[_puja_response(p) for p in rows])


@router.post("/pujas", response_model=PujaResponse, status_code=status.HTTP_201_CREATED)
async def create_puja(
    payload: PujaCreate,
    request: Request,
    p: Principal = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db_txn),
):
    _validate_price_max(payload.default_price, payload.price_max)
    await _require_category(db, payload.category_id)

    now = dt.datetime.now(dt.UTC)
    puja_id = uuid.uuid4()
    slug = slugify_name(payload.name, suffix=puja_id.hex[:8])
    puja = Puja(
        id=puja_id,
        category_id=payload.category_id,
        name=payload.name,
        slug=slug,
        tagline=payload.tagline,
        description=payload.description,
        duration_minutes=payload.duration_minutes,
        default_price=payload.default_price,
        price_max=payload.price_max,
        display_order=await _next_puja_order(db, payload.category_id),
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(puja)
    try:
        await db.flush()
    except IntegrityError:
        puja.slug = unique_slug(slug)
        try:
            await db.flush()
        except IntegrityError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, "Puja slug conflict.") from exc

    await ensure_puja_pricing_for_verified_pujaris(db, puja_id=puja.id)

    await record_admin_action(
        db,
        actor_user_id=p.user_id,
        action="create",
        entity_type="pujas",
        entity_id=str(puja.id),
        after={"name": puja.name, "slug": puja.slug, "default_price": str(puja.default_price)},
        change_reason=payload.change_reason,
        ip=_client_ip(request),
    )
    return _puja_response(puja)


@router.put("/pujas/{puja_id}", response_model=PujaResponse)
async def update_puja(
    puja_id: uuid.UUID,
    payload: PujaUpdate,
    request: Request,
    p: Principal = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db_txn),
):
    puja = await _require_puja(db, puja_id)
    before = _puja_response(puja).model_dump(mode="json")

    new_default = (
        payload.default_price
        if payload.default_price is not None
        else Decimal(str(puja.default_price))
    )
    new_max = payload.price_max if payload.price_max is not None else (
        Decimal(str(puja.price_max)) if puja.price_max is not None else None
    )
    _validate_price_max(new_default, new_max)

    if payload.category_id is not None:
        await _require_category(db, payload.category_id)
        puja.category_id = payload.category_id
    if payload.name is not None:
        puja.name = payload.name
    if payload.tagline is not None:
        puja.tagline = payload.tagline
    if payload.description is not None:
        puja.description = payload.description
    if payload.duration_minutes is not None:
        puja.duration_minutes = payload.duration_minutes
    if payload.default_price is not None:
        puja.default_price = payload.default_price
    if "price_max" in payload.model_fields_set:
        puja.price_max = payload.price_max
    if payload.is_active is not None:
        puja.is_active = payload.is_active
    if payload.hero_media_id is not None:
        puja.hero_media_id = payload.hero_media_id
    puja.updated_at = dt.datetime.now(dt.UTC)

    try:
        await db.flush()
    except IntegrityError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Puja update conflict.") from exc

    await record_admin_action(
        db,
        actor_user_id=p.user_id,
        action="update",
        entity_type="pujas",
        entity_id=str(puja.id),
        before=before,
        after=_puja_response(puja).model_dump(mode="json"),
        change_reason=payload.change_reason,
        ip=_client_ip(request),
    )
    return _puja_response(puja)


@router.get("/pujas/{puja_id}/i18n/{locale}", response_model=PujaI18nResponse)
async def get_puja_i18n(
    puja_id: uuid.UUID,
    locale: str,
    _p: Principal = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if locale not in ("te", "en"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "locale must be te or en.")
    puja = await _require_puja(db, puja_id)
    row = (
        await db.execute(
            select(PujaI18n).where(PujaI18n.puja_id == puja_id, PujaI18n.locale == locale)
        )
    ).scalar_one_or_none()
    if row is None:
        return PujaI18nResponse(
            puja_id=puja_id,
            locale=locale,  # type: ignore[arg-type]
            name=puja.name,
            tagline=puja.tagline,
            description=puja.description,
        )
    return PujaI18nResponse(
        puja_id=puja_id,
        locale=locale,  # type: ignore[arg-type]
        name=row.name,
        tagline=row.tagline,
        description=row.description,
    )


@router.put("/pujas/{puja_id}/i18n/{locale}", response_model=PujaI18nResponse)
async def upsert_puja_i18n(
    puja_id: uuid.UUID,
    locale: str,
    payload: PujaI18nUpdate,
    request: Request,
    p: Principal = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db_txn),
):
    if locale not in ("te", "en"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "locale must be te or en.")
    puja = await _require_puja(db, puja_id)
    row = (
        await db.execute(
            select(PujaI18n).where(PujaI18n.puja_id == puja_id, PujaI18n.locale == locale)
        )
    ).scalar_one_or_none()
    if row is None:
        row = PujaI18n(
            puja_id=puja_id,
            locale=locale,
            name=payload.name,
            tagline=payload.tagline,
            description=payload.description,
        )
        db.add(row)
    else:
        row.name = payload.name
        row.tagline = payload.tagline
        row.description = payload.description
    if locale == "en":
        puja.name = payload.name
        puja.tagline = payload.tagline
        puja.description = payload.description
        puja.updated_at = dt.datetime.now(dt.UTC)
    await db.flush()
    await record_admin_action(
        db,
        actor_user_id=p.user_id,
        action="i18n_update",
        entity_type="puja_i18n",
        entity_id=f"{puja_id}:{locale}",
        after={"name": payload.name, "locale": locale},
        change_reason=payload.change_reason,
        ip=_client_ip(request),
    )
    return PujaI18nResponse(
        puja_id=puja_id,
        locale=locale,  # type: ignore[arg-type]
        name=row.name,
        tagline=row.tagline,
        description=row.description,
    )


@router.get("/pujas/{puja_id}/impact", response_model=PujaImpactResponse)
async def puja_impact(
    puja_id: uuid.UUID,
    _p: Principal = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    await _require_puja(db, puja_id)
    bookings = (
        await db.execute(
            text(
                """
                SELECT count(*) FROM bookings b
                WHERE b.puja_id = :pid
                  AND b.cancelled_at IS NULL
                  AND b.scheduled_date >= CURRENT_DATE
                """
            ),
            {"pid": str(puja_id)},
        )
    ).scalar_one()
    holds = (
        await db.execute(
            text(
                """
                SELECT count(*) FROM slot_holds sh
                WHERE sh.released_at IS NULL AND sh.expires_at > now()
                """
            )
        )
    ).scalar_one()
    return PujaImpactResponse(
        puja_id=puja_id,
        active_future_bookings=int(bookings),
        active_holds_unscoped=int(holds),
    )


@router.patch("/pujas/reorder", response_model=PujaListResponse)
async def reorder_pujas(
    payload: PujaReorderRequest,
    request: Request,
    p: Principal = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db_txn),
):
    await _require_category(db, payload.category_id)
    for position, pid in enumerate(payload.ordered_ids):
        result = await db.execute(
            text(
                "UPDATE pujas SET display_order = :pos "
                "WHERE id = :id AND category_id = :cat"
            ),
            {"pos": position, "id": str(pid), "cat": payload.category_id},
        )
        if result.rowcount == 0:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Puja {pid} not found in category.")

    await record_admin_action(
        db,
        actor_user_id=p.user_id,
        action="reorder",
        entity_type="pujas",
        entity_id=str(payload.category_id),
        after={"category_id": payload.category_id, "ordered_ids": [str(x) for x in payload.ordered_ids]},
        change_reason=payload.change_reason,
        ip=_client_ip(request),
    )
    return await list_pujas(category_id=payload.category_id, _p=p, db=db)


# --------------------------------------------------------------------------- #
# Content (replace-all per kind)
# --------------------------------------------------------------------------- #
@router.get("/pujas/{puja_id}/content", response_model=ContentListResponse)
async def list_content(
    puja_id: uuid.UUID,
    kind: str = Query(...),
    locale: str = Query("en", pattern="^(te|en)$"),
    _p: Principal = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    await _require_puja(db, puja_id)
    rows = (
        await db.execute(
            select(PujaContentItem)
            .where(
                PujaContentItem.puja_id == puja_id,
                PujaContentItem.kind == kind,
                PujaContentItem.locale == locale,
                PujaContentItem.is_active.is_(True),
            )
            .order_by(PujaContentItem.position, PujaContentItem.id)
        )
    ).scalars().all()
    from app.schemas.catalog_admin import ContentItemResponse

    return ContentListResponse(
        kind=kind,  # type: ignore[arg-type]
        items=[
            ContentItemResponse(
                id=r.id, kind=r.kind, position=r.position, text=r.text, is_active=r.is_active
            )
            for r in rows
        ],
    )


@router.put("/pujas/{puja_id}/content", response_model=ContentListResponse)
async def replace_content(
    puja_id: uuid.UUID,
    payload: ContentReplaceRequest,
    request: Request,
    locale: str = Query("en", pattern="^(te|en)$"),
    p: Principal = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db_txn),
):
    await _require_puja(db, puja_id)
    await db.execute(
        delete(PujaContentItem).where(
            PujaContentItem.puja_id == puja_id,
            PujaContentItem.kind == payload.kind,
            PujaContentItem.locale == locale,
        )
    )
    for item in payload.items:
        db.add(
            PujaContentItem(
                id=uuid.uuid4(),
                puja_id=puja_id,
                kind=payload.kind,
                position=item.position,
                locale=locale,
                text=item.text,
                is_active=True,
            )
        )
    await db.flush()

    await record_admin_action(
        db,
        actor_user_id=p.user_id,
        action="content_replace",
        entity_type="puja_content_items",
        entity_id=str(puja_id),
        after={"kind": payload.kind, "locale": locale, "count": len(payload.items)},
        change_reason=payload.change_reason,
        ip=_client_ip(request),
    )
    return await list_content(puja_id, payload.kind, locale=locale, _p=p, db=db)


# --------------------------------------------------------------------------- #
# Addons
# --------------------------------------------------------------------------- #
@router.get("/pujas/{puja_id}/addons", response_model=PujaAddonListResponse)
async def list_addons(
    puja_id: uuid.UUID,
    _p: Principal = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    await _require_puja(db, puja_id)
    rows = (
        await db.execute(
            select(PujaAddon)
            .where(PujaAddon.puja_id == puja_id)
            .order_by(PujaAddon.display_order, PujaAddon.id)
        )
    ).scalars().all()
    return PujaAddonListResponse(addons=[_addon_response(a) for a in rows])


@router.post(
    "/pujas/{puja_id}/addons",
    response_model=PujaAddonResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_addon(
    puja_id: uuid.UUID,
    payload: PujaAddonCreate,
    request: Request,
    p: Principal = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db_txn),
):
    await _require_puja(db, puja_id)
    max_order = (
        await db.execute(
            select(func.coalesce(func.max(PujaAddon.display_order), -1)).where(
                PujaAddon.puja_id == puja_id
            )
        )
    ).scalar_one()
    addon = PujaAddon(
        id=uuid.uuid4(),
        puja_id=puja_id,
        name=payload.name,
        description=payload.description,
        price=payload.price,
        display_order=int(max_order) + 1,
        is_active=True,
    )
    db.add(addon)
    await db.flush()

    await record_admin_action(
        db,
        actor_user_id=p.user_id,
        action="create",
        entity_type="puja_addons",
        entity_id=str(addon.id),
        after={"name": addon.name, "price": str(addon.price)},
        change_reason=payload.change_reason,
        ip=_client_ip(request),
    )
    return _addon_response(addon)


# --------------------------------------------------------------------------- #
# Media (Wave 2 — presign + confirm)
# --------------------------------------------------------------------------- #
def _media_response(row: PujaMedia) -> MediaResponse:
    url = public_url(row.s3_key) if row.upload_status == "ready" else None
    return MediaResponse(
        id=row.id,
        entity_type=row.entity_type,  # type: ignore[arg-type]
        entity_id=row.entity_id,
        s3_key=row.s3_key,
        alt_text=row.alt_text,
        position=row.position,
        upload_status=row.upload_status,  # type: ignore[arg-type]
        is_active=row.is_active,
        public_url=url,
        created_at=row.created_at,
        confirmed_at=row.confirmed_at,
    )


def _category_id_from_entity(entity_id: uuid.UUID) -> int:
    cid = entity_id.int
    if cid < 1 or cid > 32767:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "category entity_id must encode a valid category id (1–32767).",
        )
    return cid


async def _validate_media_entity(
    db: AsyncSession, entity_type: str, entity_id: uuid.UUID
) -> None:
    if entity_type in ("puja", "gallery"):
        puja = (
            await db.execute(select(Puja.id).where(Puja.id == entity_id))
        ).scalar_one_or_none()
        if puja is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Puja not found.")
        return
    if entity_type == "category":
        cat_id = _category_id_from_entity(entity_id)
        cat = (
            await db.execute(select(PujaCategory.id).where(PujaCategory.id == cat_id))
        ).scalar_one_or_none()
        if cat is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found.")
        return
    if entity_type == "addon":
        addon = (
            await db.execute(select(PujaAddon.id).where(PujaAddon.id == entity_id))
        ).scalar_one_or_none()
        if addon is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Add-on not found.")
        return
    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid entity_type.")


@router.get("/media", response_model=MediaListResponse)
async def list_media(
    entity_type: str = Query(...),
    entity_id: uuid.UUID = Query(...),
    _p: Principal = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(PujaMedia)
            .where(
                PujaMedia.entity_type == entity_type,
                PujaMedia.entity_id == entity_id,
            )
            .order_by(PujaMedia.position, PujaMedia.created_at)
        )
    ).scalars().all()
    return MediaListResponse(items=[_media_response(r) for r in rows])


@router.post(
    "/media/presign",
    response_model=MediaPresignResponse,
    status_code=status.HTTP_201_CREATED,
)
async def presign_media(
    payload: MediaPresignRequest,
    request: Request,
    p: Principal = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db_txn),
):
    await _validate_media_entity(db, payload.entity_type, payload.entity_id)

    media_id = uuid.uuid4()
    s3_key = build_s3_key(payload.entity_type, media_id, payload.content_type)
    try:
        upload_url, expires_in = presign_catalog_put(
            s3_key=s3_key,
            content_type=payload.content_type,
            content_length=payload.content_length,
        )
    except CatalogStorageNotConfigured:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Catalogue storage is not configured (S3_ACCESS_KEY / S3_BUCKET_CATALOG).",
        ) from None
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    now = dt.datetime.now(dt.UTC)
    media = PujaMedia(
        id=media_id,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        s3_key=s3_key,
        alt_text=payload.alt_text,
        position=payload.position,
        upload_status="pending",
        is_active=False,
        created_at=now,
    )
    db.add(media)
    await db.flush()

    await record_admin_action(
        db,
        actor_user_id=p.user_id,
        action="presign",
        entity_type="puja_media",
        entity_id=str(media.id),
        after={
            "entity_type": media.entity_type,
            "entity_id": str(media.entity_id),
            "s3_key": media.s3_key,
            "content_type": payload.content_type,
        },
        change_reason=payload.change_reason,
        ip=_client_ip(request),
    )

    return MediaPresignResponse(
        media_id=media.id,
        upload_url=upload_url,
        upload_headers={"Content-Type": payload.content_type},
        expires_in=expires_in,
        s3_key=s3_key,
    )


@router.put("/media/{media_id}/upload", status_code=status.HTTP_204_NO_CONTENT)
async def upload_media_body(
    media_id: uuid.UUID,
    request: Request,
    p: Principal = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db_txn),
):
    """Server-side upload to S3 — same-origin proxy (no bucket CORS required)."""
    media = (
        await db.execute(select(PujaMedia).where(PujaMedia.id == media_id))
    ).scalar_one_or_none()
    if media is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Media not found.")
    if media.upload_status != "pending":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Media is not pending (status={media.upload_status}).",
        )

    ext = media.s3_key.rsplit(".", 1)[-1].lower()
    ext_to_type = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
    }
    expected_type = ext_to_type.get(ext)
    if not expected_type:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Invalid media key.")

    content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if content_type != expected_type:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Content-Type must be {expected_type}.",
        )

    body = await request.body()
    try:
        put_catalog_object(s3_key=media.s3_key, body=body, content_type=content_type)
    except CatalogStorageNotConfigured:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Catalogue storage is not configured.",
        ) from None
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except CatalogMediaError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    await record_admin_action(
        db,
        actor_user_id=p.user_id,
        action="upload",
        entity_type="puja_media",
        entity_id=str(media.id),
        after={"s3_key": media.s3_key, "bytes": len(body)},
        ip=_client_ip(request),
    )


@router.post("/media/{media_id}/confirm", response_model=MediaResponse)
async def confirm_media(
    media_id: uuid.UUID,
    request: Request,
    p: Principal = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db_txn),
):
    media = (
        await db.execute(select(PujaMedia).where(PujaMedia.id == media_id))
    ).scalar_one_or_none()
    if media is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Media not found.")

    if media.upload_status == "ready":
        return _media_response(media)

    if media.upload_status == "failed":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Media upload previously failed; request a new presign.",
        )

    # Infer expected content type from s3_key extension
    ext = media.s3_key.rsplit(".", 1)[-1].lower()
    ext_to_type = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
    }
    expected_type = ext_to_type.get(ext)
    if not expected_type:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Invalid media key.")

    try:
        head = head_catalog_object(media.s3_key)
        validate_head_for_confirm(head=head, expected_content_type=expected_type)
    except CatalogStorageNotConfigured:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Catalogue storage is not configured.",
        ) from None
    except CatalogMediaError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    before = _media_response(media).model_dump(mode="json")
    now = dt.datetime.now(dt.UTC)
    media.upload_status = "ready"
    media.is_active = True
    media.confirmed_at = now
    await db.flush()

    await record_admin_action(
        db,
        actor_user_id=p.user_id,
        action="confirm",
        entity_type="puja_media",
        entity_id=str(media.id),
        before=before,
        after=_media_response(media).model_dump(mode="json"),
        ip=_client_ip(request),
    )
    return _media_response(media)


@router.put("/addons/{addon_id}", response_model=PujaAddonResponse)
async def update_addon(
    addon_id: uuid.UUID,
    payload: PujaAddonUpdate,
    request: Request,
    p: Principal = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db_txn),
):
    addon = (
        await db.execute(select(PujaAddon).where(PujaAddon.id == addon_id))
    ).scalar_one_or_none()
    if addon is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Add-on not found.")

    if all(
        v is None
        for v in (
            payload.name,
            payload.description,
            payload.price,
            payload.is_active,
            payload.image_media_id,
        )
    ):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No fields to update.")

    before = _addon_response(addon).model_dump(mode="json")
    if payload.name is not None:
        addon.name = payload.name
    if payload.description is not None:
        addon.description = payload.description
    if payload.price is not None:
        addon.price = payload.price
    if payload.is_active is not None:
        addon.is_active = payload.is_active
    if "image_media_id" in payload.model_fields_set:
        addon.image_media_id = payload.image_media_id
    await db.flush()

    await record_admin_action(
        db,
        actor_user_id=p.user_id,
        action="update",
        entity_type="puja_addons",
        entity_id=str(addon.id),
        before=before,
        after=_addon_response(addon).model_dump(mode="json"),
        change_reason=payload.change_reason,
        ip=_client_ip(request),
    )
    return _addon_response(addon)
