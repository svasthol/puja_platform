"""Sprint 4-0 admin control-plane tests — P-ADMIN-ROLE + P-ADMIN-SEED + P-ADMIN-AUTH.

Handlers are invoked directly with the live-DB `session` fixture and an explicit
Principal (the same style as test_sprint40_auth.py); the dependency chain
(get_principal / require_admin_role) is exercised in its own tests. Redis rate
limiting is patched out — the logic under test is ours.

Requires migration 009 applied (roles catalogue, admin_credentials, admin_audit_log).
"""
from __future__ import annotations

import time
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import text

from app.api.v1.endpoints import admin as admin_ep
from app.api.v1.endpoints import admin_auth as admin_auth_ep
from app.core import crypto, totp
from app.core.config import get_settings
from app.core.dependencies import Principal, get_principal
from app.core.security import (
    access_ttl_minutes,
    create_access_token,
    decode_token,
    refresh_ttl_days,
)
from app.schemas.admin import AdvanceAmountUpdate, RoleAssignRequest
from app.schemas.admin_auth import AdminLoginRequest


# --------------------------------------------------------------------------- #
# fixtures / helpers
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def totp_key():
    """Provide a Fernet key so crypto works; restore afterwards."""
    settings = get_settings()
    original = settings.TOTP_ENC_KEYS
    settings.TOTP_ENC_KEYS = Fernet.generate_key().decode()
    crypto._keys.cache_clear()
    yield
    settings.TOTP_ENC_KEYS = original
    crypto._keys.cache_clear()


class _FakeRequest:
    """Minimal stand-in for starlette Request — only .client.host is read."""

    client = None


def _uniq_phone() -> str:
    return "+91966" + uuid.uuid4().hex[:7]


async def _mk_user(session, phone: str) -> uuid.UUID:
    uid = uuid.uuid4()
    await session.execute(
        text("INSERT INTO users (id, full_name, phone) VALUES (:id, 'T', :ph)"),
        {"id": str(uid), "ph": phone},
    )
    return uid


async def _grant_role(session, user_id: uuid.UUID, role_name: str) -> None:
    await session.execute(
        text("INSERT INTO roles (name) VALUES (:n) ON CONFLICT (name) DO NOTHING"),
        {"n": role_name},
    )
    rid = (
        await session.execute(text("SELECT id FROM roles WHERE name = :n"), {"n": role_name})
    ).scalar_one()
    await session.execute(
        text(
            "INSERT INTO user_roles (user_id, role_id, assigned_at) "
            "VALUES (:u, :r, now()) ON CONFLICT DO NOTHING"
        ),
        {"u": str(user_id), "r": rid},
    )


def _admin(uid: uuid.UUID, *roles: str) -> Principal:
    return Principal(user_id=uid, app_context="admin", roles=roles or ("admin",))


# --------------------------------------------------------------------------- #
# P-ADMIN-ROLE — dependency loads roles, gates issuance
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_get_principal_loads_admin_roles(session):
    uid = await _mk_user(session, _uniq_phone())
    await _grant_role(session, uid, "admin")
    await session.commit()

    token = create_access_token(subject=str(uid), app_context="admin")
    principal = await get_principal(
        credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials=token),
        db=session,
    )
    assert principal.app_context == "admin"
    assert "admin" in principal.roles
    assert principal.has_role("admin")


@pytest.mark.asyncio
async def test_admin_token_without_role_is_forbidden(session):
    """An admin-context token for a user with no role -> 403 (revocation takes
    effect within one access-token lifetime, no refresh needed)."""
    uid = await _mk_user(session, _uniq_phone())
    await session.commit()
    token = create_access_token(subject=str(uid), app_context="admin")
    with pytest.raises(HTTPException) as exc:
        await get_principal(
            credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials=token),
            db=session,
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_customer_token_carries_no_roles(session):
    uid = await _mk_user(session, _uniq_phone())
    await session.commit()
    token = create_access_token(subject=str(uid), app_context="customer")
    principal = await get_principal(
        credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials=token),
        db=session,
    )
    assert principal.roles == ()


def test_admin_token_ttls_are_short():
    assert access_ttl_minutes("admin") == get_settings().ADMIN_ACCESS_TOKEN_EXPIRE_MINUTES
    assert refresh_ttl_days("admin") == get_settings().ADMIN_REFRESH_TOKEN_EXPIRE_DAYS
    assert access_ttl_minutes("customer") == get_settings().ACCESS_TOKEN_EXPIRE_MINUTES
    assert refresh_ttl_days("pujari") == get_settings().REFRESH_TOKEN_EXPIRE_DAYS
    assert refresh_ttl_days("admin") < refresh_ttl_days("customer")


# --------------------------------------------------------------------------- #
# P-ADMIN-SEED — role assignment endpoints (admin only), all audited
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_admin_me_returns_session(session):
    uid = await _mk_user(session, _uniq_phone())
    await _grant_role(session, uid, "admin")
    await session.commit()
    token = create_access_token(subject=str(uid), app_context="admin")
    principal = await get_principal(
        credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials=token),
        db=session,
    )
    resp = await admin_ep.admin_me(p=principal, db=session)
    assert resp.user_id == uid
    assert "admin" in resp.roles
    assert resp.is_admin is True


@pytest.mark.asyncio
async def test_assign_role_creates_row_and_audit(session):
    actor = await _mk_user(session, _uniq_phone())
    target = await _mk_user(session, _uniq_phone())
    await session.commit()

    resp = await admin_ep.assign_role(
        target,
        RoleAssignRequest(role="support", change_reason="onboarding"),
        _FakeRequest(),
        p=_admin(actor),
        db=session,
    )
    await session.commit()
    assert "support" in resp.roles

    audit = (
        await session.execute(
            text(
                "SELECT action, entity_type, change_reason FROM admin_audit_log "
                "WHERE actor_user_id = :a AND entity_id = :e ORDER BY created_at DESC LIMIT 1"
            ),
            {"a": str(actor), "e": str(target)},
        )
    ).mappings().first()
    assert audit["action"] == "role_assign"
    assert audit["entity_type"] == "user_roles"
    assert audit["change_reason"] == "onboarding"


@pytest.mark.asyncio
async def test_assign_role_is_idempotent(session):
    actor = await _mk_user(session, _uniq_phone())
    target = await _mk_user(session, _uniq_phone())
    await session.commit()
    for _ in range(2):
        resp = await admin_ep.assign_role(
            target, RoleAssignRequest(role="support"), _FakeRequest(),
            p=_admin(actor), db=session,
        )
        await session.commit()
    assert resp.roles.count("support") == 1


@pytest.mark.asyncio
async def test_revoke_role(session):
    actor = await _mk_user(session, _uniq_phone())
    target = await _mk_user(session, _uniq_phone())
    await _grant_role(session, target, "support")
    await session.commit()

    resp = await admin_ep.revoke_role(
        target, "support", _FakeRequest(), p=_admin(actor), db=session
    )
    await session.commit()
    assert "support" not in resp.roles


@pytest.mark.asyncio
async def test_last_admin_guard(session):
    """Removing the final admin globally is blocked; if others exist, it succeeds."""
    actor = await _mk_user(session, _uniq_phone())
    target = await _mk_user(session, _uniq_phone())
    await _grant_role(session, target, "admin")
    await session.commit()

    others = (
        await session.execute(
            text(
                "SELECT count(*) FROM user_roles ur JOIN roles r ON r.id = ur.role_id "
                "WHERE r.name = 'admin' AND ur.user_id != :t"
            ),
            {"t": str(target)},
        )
    ).scalar_one()

    if others == 0:
        with pytest.raises(HTTPException) as exc:
            await admin_ep.revoke_role(
                target, "admin", _FakeRequest(), p=_admin(actor), db=session
            )
        assert exc.value.status_code == 409
        await session.rollback()
    else:
        resp = await admin_ep.revoke_role(
            target, "admin", _FakeRequest(), p=_admin(actor), db=session
        )
        await session.commit()
        assert "admin" not in resp.roles


@pytest.mark.asyncio
async def test_assign_unknown_user_404(session):
    actor = await _mk_user(session, _uniq_phone())
    await session.commit()
    with pytest.raises(HTTPException) as exc:
        await admin_ep.assign_role(
            uuid.uuid4(), RoleAssignRequest(role="support"), _FakeRequest(),
            p=_admin(actor), db=session,
        )
    assert exc.value.status_code == 404


# --------------------------------------------------------------------------- #
# advance-amount now audited
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_set_advance_writes_audit(session):
    actor = await _mk_user(session, _uniq_phone())
    await session.commit()
    await admin_ep.set_advance(
        AdvanceAmountUpdate(amount=501, change_reason="peak season"),
        _FakeRequest(),
        p=_admin(actor),
        db=session,
    )
    await session.commit()
    audit = (
        await session.execute(
            text(
                "SELECT action, after_json FROM admin_audit_log "
                "WHERE actor_user_id = :a AND entity_type = 'platform_settings' "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"a": str(actor)},
        )
    ).mappings().first()
    assert audit["action"] == "update"
    assert audit["after_json"]["amount"] == "501"


# --------------------------------------------------------------------------- #
# P-ADMIN-AUTH — provisioning + TOTP login + replay
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_provision_requires_admin_role_on_target(session):
    actor = await _mk_user(session, _uniq_phone())
    target = await _mk_user(session, _uniq_phone())  # no role
    await session.commit()
    with pytest.raises(HTTPException) as exc:
        await admin_ep.provision_credential(
            target, _FakeRequest(), p=_admin(actor), db=session
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_provision_then_login_activates_and_blocks_replay(session):
    actor = await _mk_user(session, _uniq_phone())
    phone = _uniq_phone()
    target = await _mk_user(session, phone)
    await _grant_role(session, target, "admin")
    await session.commit()

    prov = await admin_ep.provision_credential(
        target, _FakeRequest(), p=_admin(actor), db=session
    )
    await session.commit()
    assert prov.provisioning_uri.startswith("otpauth://")
    secret = prov.secret

    # credential exists but not yet activated
    activated = (
        await session.execute(
            text("SELECT activated_at FROM admin_credentials WHERE user_id = :u"),
            {"u": str(target)},
        )
    ).scalar_one()
    assert activated is None

    code = totp.totp_at(secret, at=int(time.time()))
    with patch.object(admin_auth_ep, "_rate_limit", new_callable=AsyncMock):
        pair = await admin_auth_ep.admin_login(
            AdminLoginRequest(phone=phone, code=code), _FakeRequest(), db=session
        )
        await session.commit()
        # admin token minted with admin context + short TTL
        claims = decode_token(pair.access_token)
        assert claims["app_context"] == "admin"

        # activated + replay guard set
        cred = (
            await session.execute(
                text(
                    "SELECT activated_at, last_used_step FROM admin_credentials "
                    "WHERE user_id = :u"
                ),
                {"u": str(target)},
            )
        ).mappings().first()
        assert cred["activated_at"] is not None
        assert cred["last_used_step"] > 0

        # replay the SAME code -> rejected
        with pytest.raises(HTTPException) as exc:
            await admin_auth_ep.admin_login(
                AdminLoginRequest(phone=phone, code=code), _FakeRequest(), db=session
            )
        assert exc.value.status_code == 401
        await session.rollback()


@pytest.mark.asyncio
async def test_admin_login_no_credential_401(session):
    phone = _uniq_phone()
    uid = await _mk_user(session, phone)
    await _grant_role(session, uid, "admin")
    await session.commit()
    with patch.object(admin_auth_ep, "_rate_limit", new_callable=AsyncMock):
        with pytest.raises(HTTPException) as exc:
            await admin_auth_ep.admin_login(
                AdminLoginRequest(phone=phone, code="123456"), _FakeRequest(), db=session
            )
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_admin_login_wrong_code_401(session):
    actor = await _mk_user(session, _uniq_phone())
    phone = _uniq_phone()
    target = await _mk_user(session, phone)
    await _grant_role(session, target, "admin")
    await session.commit()
    await admin_ep.provision_credential(target, _FakeRequest(), p=_admin(actor), db=session)
    await session.commit()
    with patch.object(admin_auth_ep, "_rate_limit", new_callable=AsyncMock):
        with pytest.raises(HTTPException) as exc:
            await admin_auth_ep.admin_login(
                AdminLoginRequest(phone=phone, code="000000"), _FakeRequest(), db=session
            )
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_admin_login_without_role_401(session):
    """A user with a credential but no admin role cannot get an admin token
    (issuance gate) — generic 401, no enumeration."""
    actor = await _mk_user(session, _uniq_phone())
    phone = _uniq_phone()
    target = await _mk_user(session, phone)
    await _grant_role(session, target, "support")  # give role to provision
    await session.commit()
    prov = await admin_ep.provision_credential(
        target, _FakeRequest(), p=_admin(actor), db=session
    )
    await session.commit()

    # revoke the role — credential remains, but login must now fail
    await session.execute(
        text("DELETE FROM user_roles WHERE user_id = :u"), {"u": str(target)}
    )
    await session.commit()

    code = totp.totp_at(prov.secret, at=int(time.time()))
    with patch.object(admin_auth_ep, "_rate_limit", new_callable=AsyncMock):
        with pytest.raises(HTTPException) as exc:
            await admin_auth_ep.admin_login(
                AdminLoginRequest(phone=phone, code=code), _FakeRequest(), db=session
            )
    assert exc.value.status_code == 401
