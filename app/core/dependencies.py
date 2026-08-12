"""
Shared FastAPI dependencies: authentication, app_context enforcement, and the
principal identity used by every protected route.

project.mdc: "app_context is checked on every authenticated request. A
customer-app token calling a pujari endpoint -> 403."
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import jwt
import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import redis_getdel
from app.core.security import decode_token
from app.db.engine import get_db
from app.models.identity import User, UserRole
from app.models.lookups import Role

log = structlog.get_logger()

ADMIN_ROLES = ("admin", "support")


@dataclass
class Principal:
    user_id: uuid.UUID
    app_context: str  # 'customer' | 'pujari' | 'admin'
    roles: tuple[str, ...] = field(default_factory=tuple)

    def has_role(self, *names: str) -> bool:
        return any(r in self.roles for r in names)


bearer_scheme = HTTPBearer(auto_error=False)


async def get_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Principal:
    if credentials is None:
        log.warning("auth_failed", reason="missing_bearer")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = credentials.credentials
    try:
        claims = decode_token(token)
    except jwt.ExpiredSignatureError:
        log.warning("auth_failed", reason="token_expired")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired")
    except jwt.PyJWTError:
        log.warning("auth_failed", reason="invalid_token")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")

    if claims.get("type") != "access":
        log.warning("auth_failed", reason="not_access_token")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not an access token")

    try:
        user_id = uuid.UUID(str(claims["sub"]))
    except (KeyError, ValueError):
        log.warning("auth_failed", reason="malformed_subject")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Malformed subject")

    app_context = claims.get("app_context")
    if app_context not in ("customer", "pujari", "admin"):
        log.warning("auth_failed", reason="missing_app_context")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing app_context")

    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None or not user.is_active:
        log.warning("auth_failed", reason="user_inactive_or_unknown", user_id=str(user_id))
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User inactive or unknown")

    # P-ADMIN-ROLE: load roles ONLY for admin-context tokens. A global lookup
    # would add a join to every customer/pujari request AND — since neither has
    # user_roles rows — is simply unnecessary. An admin token whose roles were
    # revoked after issuance is rejected here, so revocation takes effect within
    # one access-token lifetime (≤ 30 min) without waiting for refresh.
    roles: tuple[str, ...] = ()
    if app_context == "admin":
        rows = (
            await db.execute(
                select(Role.name)
                .join(UserRole, UserRole.role_id == Role.id)
                .where(UserRole.user_id == user_id)
            )
        ).scalars().all()
        roles = tuple(rows)
        if not any(r in ADMIN_ROLES for r in roles):
            log.warning("auth_failed", reason="admin_token_without_role", user_id=str(user_id))
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Admin access revoked. Contact an administrator.",
            )

    return Principal(user_id=user_id, app_context=app_context, roles=roles)


def require_context(*allowed: str):
    """Dependency factory enforcing app_context. Customer token on a pujari
    route -> 403, per project.mdc."""

    async def _dep(principal: Principal = Depends(get_principal)) -> Principal:
        if principal.app_context not in allowed:
            log.warning(
                "auth_context_denied",
                required=list(allowed),
                actual=principal.app_context,
                user_id=str(principal.user_id),
            )
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"This endpoint requires app_context in {allowed}, "
                f"token has '{principal.app_context}'.",
            )
        return principal

    return _dep


require_customer = require_context("customer")
require_pujari = require_context("pujari")
require_admin = require_context("admin")
require_customer_or_pujari = require_context("customer", "pujari")


def require_roles(*allowed: str):
    """Dependency factory for role-gated admin actions (RBAC matrix, ADMIN.md).

    Assumes app_context=admin already (roles are only loaded there). Use for
    admin-only actions like role assignment / catalogue writes that `support`
    must not perform. Layer on top of require_admin at the router.
    """

    async def _dep(principal: Principal = Depends(require_admin)) -> Principal:
        if not principal.has_role(*allowed):
            log.warning(
                "auth_role_denied",
                required=list(allowed),
                actual=list(principal.roles),
                user_id=str(principal.user_id),
            )
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"This action requires role in {allowed}.",
            )
        return principal

    return _dep


require_admin_role = require_roles("admin")  # strictly 'admin', not 'support'


# ---- WebSocket ticket auth (single-use Redis GETDEL) ----------------------
async def resolve_ws_ticket(ticket: str) -> Principal:
    """Consume a single-use WS ticket. Bearer tokens never appear in WS URLs."""
    import json

    raw = await redis_getdel(f"ws_ticket:{ticket}")
    if raw is None:
        log.warning("ws_ticket_invalid", reason="missing_or_already_used")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or used ticket")
    data = json.loads(raw)
    return Principal(user_id=uuid.UUID(data["user_id"]), app_context=data["app_context"])
