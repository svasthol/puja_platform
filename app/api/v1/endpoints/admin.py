"""Admin panel endpoints (role=admin/support). Every mutation is audited.

RBAC (ADMIN.md matrix):
  * read actions  -> require_admin           (admin OR support)
  * write actions -> require_admin_role      (admin ONLY; support is read-mostly)

Role assignment and TOTP provisioning are admin-only and self-audited. Every
mutation writes an admin_audit_log row in the SAME transaction (A-AUDIT-LOG):
if the write rolls back, its audit row rolls back too.
"""
from __future__ import annotations

import datetime as dt
import json
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import current_key_version, encrypt_secret
from app.core.dependencies import (
    ADMIN_ROLES,
    Principal,
    require_admin,
    require_admin_role,
)
from app.core import totp
from app.core.config import get_settings
from app.db.engine import get_db, get_db_txn
from app.models.admin import AdminCredential
from app.models.identity import User, UserRole
from app.models.lookups import Role
from app.schemas.admin import (
    AdvanceAmountResponse,
    AdvanceAmountUpdate,
    BookingFeeResponse,
    BookingFeeUpdate,
    AdminMeResponse,
    CredentialProvisionResponse,
    RoleAssignRequest,
    TdsFacilitationResponse,
    TdsFacilitationUpdate,
    UserRolesResponse,
)
from app.services.pricing import (
    ALLOWED_ENTITY_TYPES,
    TDS_FACILITATION_SETTINGS_KEY,
    default_tds_facilitation_config,
    parse_tds_facilitation_config,
)
from app.services.audit import record_admin_action

router = APIRouter(prefix="/admin", tags=["admin"])
settings = get_settings()


async def _roles_for(db: AsyncSession, user_id: uuid.UUID) -> list[str]:
    rows = (
        await db.execute(
            select(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id)
            .order_by(Role.name)
        )
    ).scalars().all()
    return list(rows)


async def _require_user(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
    return user


@router.get("/me", response_model=AdminMeResponse)
async def admin_me(p: Principal = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Current admin session — roles from DB (not JWT) for accurate RBAC nav."""
    user = await _require_user(db, p.user_id)
    roles = list(p.roles)
    return AdminMeResponse(
        user_id=p.user_id,
        phone=user.phone,
        roles=roles,
        is_admin="admin" in roles,
        is_support="support" in roles,
    )


# --------------------------------------------------------------------------- #
# Platform settings — advance booking amount
# --------------------------------------------------------------------------- #
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
    request: Request,
    p: Principal = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db_txn),
):
    before = (
        await db.execute(
            text("SELECT value_json FROM platform_settings WHERE key='advance_booking_amount'")
        )
    ).scalar_one_or_none()
    await db.execute(
        text(
            "UPDATE platform_settings SET "
            "value_json = jsonb_build_object('amount', CAST(:amt AS numeric), 'currency', 'INR'), "
            "updated_at = now() WHERE key='advance_booking_amount'"
        ),
        {"amt": str(payload.amount)},
    )
    await record_admin_action(
        db,
        actor_user_id=p.user_id,
        action="update",
        entity_type="platform_settings",
        entity_id="advance_booking_amount",
        before={"value": before} if before is not None else None,
        after={"amount": str(payload.amount), "currency": "INR"},
        change_reason=payload.change_reason,
        ip=request.client.host if request.client else None,
    )
    return AdvanceAmountResponse(amount=payload.amount, currency="INR")


@router.get("/settings/booking-fee", response_model=BookingFeeResponse)
async def get_booking_fee(_p: Principal = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (
        await db.execute(
            text(
                "SELECT value_json, updated_at FROM platform_settings WHERE key='booking_fee'"
            )
        )
    ).mappings().first()
    if row is None:
        from app.services.pricing import BOOKING_FEE_LABEL

        return BookingFeeResponse(
            amount=Decimal(str(settings.DEFAULT_BOOKING_FEE)),
            currency="INR",
            label=BOOKING_FEE_LABEL,
        )
    payload = row["value_json"]
    return BookingFeeResponse(
        amount=Decimal(str(payload["amount"])),
        currency=payload.get("currency", "INR"),
        label=payload.get("label", "Muhurat & Slot Lock Token"),
        updated_at=str(row["updated_at"]) if row.get("updated_at") else None,
    )


@router.put("/settings/booking-fee", response_model=BookingFeeResponse)
async def set_booking_fee(
    payload: BookingFeeUpdate,
    request: Request,
    p: Principal = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db_txn),
):
    before = (
        await db.execute(
            text("SELECT value_json FROM platform_settings WHERE key='booking_fee'")
        )
    ).scalar_one_or_none()
    label = payload.label or (before or {}).get("label") or "Muhurat & Slot Lock Token"
    await db.execute(
        text(
            """
            INSERT INTO platform_settings (key, value_json, updated_at)
            VALUES (
                'booking_fee',
                jsonb_build_object(
                    'amount', CAST(:amt AS numeric),
                    'currency', 'INR',
                    'label', :label
                ),
                now()
            )
            ON CONFLICT (key) DO UPDATE SET
                value_json = jsonb_build_object(
                    'amount', CAST(:amt AS numeric),
                    'currency', 'INR',
                    'label', :label
                ),
                updated_at = now()
            """
        ),
        {"amt": str(payload.amount), "label": label},
    )
    await record_admin_action(
        db,
        actor_user_id=p.user_id,
        action="update",
        entity_type="platform_settings",
        entity_id="booking_fee",
        before={"value": before} if before is not None else None,
        after={"amount": str(payload.amount), "currency": "INR", "label": label},
        change_reason=payload.change_reason,
        ip=request.client.host if request.client else None,
    )
    return BookingFeeResponse(amount=payload.amount, currency="INR", label=label)


def _tds_facilitation_response(
    cfg,
    *,
    updated_at: str | None = None,
) -> TdsFacilitationResponse:
    return TdsFacilitationResponse(
        no_pan_rate_pct=cfg.no_pan_rate_pct,
        pan_entity_rate_pct=cfg.pan_entity_rate_pct,
        individual_fy_threshold_inr=cfg.individual_fy_threshold_inr,
        fy_turnover_warn_inr=cfg.fy_turnover_warn_inr,
        fy_turnover_block_inr=cfg.fy_turnover_block_inr,
        always_taxed_entity_types=sorted(cfg.always_taxed_entity_types),
        updated_at=updated_at,
    )


@router.get("/settings/tds-facilitation", response_model=TdsFacilitationResponse)
async def get_tds_facilitation(
    _p: Principal = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    row = (
        await db.execute(
            text(
                "SELECT value_json, updated_at FROM platform_settings "
                "WHERE key=:key"
            ),
            {"key": TDS_FACILITATION_SETTINGS_KEY},
        )
    ).mappings().first()
    cfg = parse_tds_facilitation_config(row["value_json"] if row else None)
    updated_at = str(row["updated_at"]) if row and row.get("updated_at") else None
    return _tds_facilitation_response(cfg, updated_at=updated_at)


@router.put("/settings/tds-facilitation", response_model=TdsFacilitationResponse)
async def set_tds_facilitation(
    payload: TdsFacilitationUpdate,
    request: Request,
    p: Principal = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db_txn),
):
    if payload.fy_turnover_warn_inr >= payload.fy_turnover_block_inr:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "fy_turnover_warn_inr must be less than fy_turnover_block_inr",
        )
    invalid = [t for t in payload.always_taxed_entity_types if t not in ALLOWED_ENTITY_TYPES]
    if invalid:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Invalid entity types: {', '.join(invalid)}",
        )
    before = (
        await db.execute(
            text("SELECT value_json FROM platform_settings WHERE key=:key"),
            {"key": TDS_FACILITATION_SETTINGS_KEY},
        )
    ).scalar_one_or_none()
    value_json = {
        "no_pan_rate_pct": str(payload.no_pan_rate_pct),
        "pan_entity_rate_pct": str(payload.pan_entity_rate_pct),
        "individual_fy_threshold_inr": str(payload.individual_fy_threshold_inr),
        "fy_turnover_warn_inr": str(payload.fy_turnover_warn_inr),
        "fy_turnover_block_inr": str(payload.fy_turnover_block_inr),
        "always_taxed_entity_types": payload.always_taxed_entity_types,
    }
    await db.execute(
        text(
            """
            INSERT INTO platform_settings (key, value_json, updated_at)
            VALUES (:key, CAST(:value_json AS jsonb), now())
            ON CONFLICT (key) DO UPDATE SET
                value_json = CAST(:value_json AS jsonb),
                updated_at = now()
            """
        ),
        {"key": TDS_FACILITATION_SETTINGS_KEY, "value_json": json.dumps(value_json)},
    )
    cfg = parse_tds_facilitation_config(value_json)
    await record_admin_action(
        db,
        actor_user_id=p.user_id,
        action="update",
        entity_type="platform_settings",
        entity_id=TDS_FACILITATION_SETTINGS_KEY,
        before={"value": before} if before is not None else None,
        after=value_json,
        change_reason=payload.change_reason,
        ip=request.client.host if request.client else None,
    )
    return _tds_facilitation_response(cfg)


# --------------------------------------------------------------------------- #
# Role management (P-ADMIN-SEED) — admin only
# --------------------------------------------------------------------------- #
@router.get("/users/{user_id}/roles", response_model=UserRolesResponse)
async def list_user_roles(
    user_id: uuid.UUID,
    _p: Principal = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    await _require_user(db, user_id)
    return UserRolesResponse(user_id=user_id, roles=await _roles_for(db, user_id))


@router.post(
    "/users/{user_id}/roles",
    response_model=UserRolesResponse,
    status_code=status.HTTP_201_CREATED,
)
async def assign_role(
    user_id: uuid.UUID,
    payload: RoleAssignRequest,
    request: Request,
    p: Principal = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db_txn),
):
    await _require_user(db, user_id)
    role_id = (
        await db.execute(select(Role.id).where(Role.name == payload.role))
    ).scalar_one_or_none()
    if role_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown role '{payload.role}'.")

    exists = (
        await db.execute(
            select(UserRole).where(
                UserRole.user_id == user_id, UserRole.role_id == role_id
            )
        )
    ).scalar_one_or_none()
    if exists is None:
        db.add(
            UserRole(
                user_id=user_id,
                role_id=role_id,
                assigned_at=dt.datetime.now(dt.UTC),
            )
        )
        await db.flush()
        await record_admin_action(
            db,
            actor_user_id=p.user_id,
            action="role_assign",
            entity_type="user_roles",
            entity_id=str(user_id),
            after={"role": payload.role},
            change_reason=payload.change_reason,
            ip=request.client.host if request.client else None,
        )
    return UserRolesResponse(user_id=user_id, roles=await _roles_for(db, user_id))


@router.delete("/users/{user_id}/roles/{role}", response_model=UserRolesResponse)
async def revoke_role(
    user_id: uuid.UUID,
    role: str,
    request: Request,
    p: Principal = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db_txn),
):
    await _require_user(db, user_id)
    role_id = (
        await db.execute(select(Role.id).where(Role.name == role))
    ).scalar_one_or_none()
    if role_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown role '{role}'.")

    # Lockout guard: never remove the last 'admin' in the system. Losing every
    # admin bricks the whole control plane (only an admin can grant roles).
    if role == "admin":
        admin_count = (
            await db.execute(
                select(func.count())
                .select_from(UserRole)
                .join(Role, Role.id == UserRole.role_id)
                .where(Role.name == "admin")
            )
        ).scalar_one()
        target_is_admin = (
            await db.execute(
                select(UserRole).where(
                    UserRole.user_id == user_id, UserRole.role_id == role_id
                )
            )
        ).scalar_one_or_none() is not None
        if target_is_admin and admin_count <= 1:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Cannot remove the last admin. Assign another admin first.",
            )

    result = await db.execute(
        text("DELETE FROM user_roles WHERE user_id = :uid AND role_id = :rid"),
        {"uid": str(user_id), "rid": role_id},
    )
    if result.rowcount:
        await record_admin_action(
            db,
            actor_user_id=p.user_id,
            action="role_revoke",
            entity_type="user_roles",
            entity_id=str(user_id),
            before={"role": role},
            ip=request.client.host if request.client else None,
        )
    return UserRolesResponse(user_id=user_id, roles=await _roles_for(db, user_id))


# --------------------------------------------------------------------------- #
# TOTP credential provisioning (P-ADMIN-AUTH) — admin only, admin-vouched
# --------------------------------------------------------------------------- #
@router.post(
    "/users/{user_id}/credential",
    response_model=CredentialProvisionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def provision_credential(
    user_id: uuid.UUID,
    request: Request,
    p: Principal = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db_txn),
):
    """Generate (or reset) a target admin's TOTP secret. Secret shown ONCE.

    Admin-vouched provisioning replaces phone-only self-enrolment — it closes
    the enrolment race and keeps SMS/DLT out of the admin path entirely. Used
    for onboarding a new admin and for resetting a lost authenticator.
    """
    user = await _require_user(db, user_id)
    roles = await _roles_for(db, user_id)
    if not any(r in ADMIN_ROLES for r in roles):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Assign an admin/support role before provisioning a credential.",
        )

    secret = totp.generate_secret()
    now = dt.datetime.now(dt.UTC)
    cred = (
        await db.execute(
            select(AdminCredential).where(AdminCredential.user_id == user_id).with_for_update()
        )
    ).scalar_one_or_none()
    reset = cred is not None
    if cred is None:
        cred = AdminCredential(user_id=user_id, enrolled_at=now)
        db.add(cred)
    cred.totp_secret_enc = encrypt_secret(secret)
    cred.key_version = current_key_version()
    cred.activated_at = None          # re-activate on first successful login
    cred.last_used_step = 0
    cred.updated_at = now

    await record_admin_action(
        db,
        actor_user_id=p.user_id,
        action="credential_reset" if reset else "credential_provision",
        entity_type="admin_credentials",
        entity_id=str(user_id),
        change_reason=None,
        ip=request.client.host if request.client else None,
    )

    uri = totp.provisioning_uri(
        secret,
        account_name=user.phone,
        issuer=settings.TOTP_ISSUER,
        step=settings.TOTP_STEP_SECONDS,
    )
    return CredentialProvisionResponse(user_id=user_id, provisioning_uri=uri, secret=secret)
