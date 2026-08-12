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
    AdminMeResponse,
    CredentialProvisionResponse,
    RoleAssignRequest,
    UserRolesResponse,
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
