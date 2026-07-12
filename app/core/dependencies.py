"""
Shared FastAPI dependencies: authentication, app_context enforcement, and the
principal identity used by every protected route.

project.mdc: "app_context is checked on every authenticated request. A
customer-app token calling a pujari endpoint -> 403."
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

import jwt
import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import redis_getdel
from app.core.security import decode_token
from app.db.engine import get_db
from app.models.identity import User

log = structlog.get_logger()


@dataclass
class Principal:
    user_id: uuid.UUID
    app_context: str  # 'customer' | 'pujari' | 'admin'
    roles: tuple[str, ...] = ()


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

    return Principal(user_id=user_id, app_context=app_context)


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
