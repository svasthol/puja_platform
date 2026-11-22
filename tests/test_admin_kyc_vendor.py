"""Admin console KYC vendor switch (platform_settings.kyc_vendor)."""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import text

from app.api.v1.endpoints import admin as admin_ep
from app.core.config import get_settings
from app.core.dependencies import Principal
from app.schemas.admin import KycVendorUpdate
from app.services import partner_kyc_service as kyc_svc
from app.services.kyc_vendor import (
    KYC_VENDOR_SETTING_KEY,
    active_kyc_vendor_name,
    invalidate_active_kyc_vendor_cache,
)
from tests.test_partner_kyc_digilocker import _FakeVendor, _seed_pujari


class _FakeRequest:
    client = None


async def _clear_setting(session) -> None:
    await session.execute(
        text("DELETE FROM platform_settings WHERE key = :k"), {"k": KYC_VENDOR_SETTING_KEY}
    )
    await session.commit()
    invalidate_active_kyc_vendor_cache()


@pytest_asyncio.fixture
async def clean_kyc_vendor_setting(session):
    await _clear_setting(session)
    yield
    await _clear_setting(session)


@pytest.fixture
def both_vendors_configured():
    s = get_settings()
    with (
        patch.object(s, "KYC_VENDOR", "setu_digilocker"),
        patch.object(s, "KYC_APISATHI_API_KEY", "test_key"),
        patch.object(s, "KYC_SETU_CLIENT_ID", "cid"),
        patch.object(s, "KYC_SETU_CLIENT_SECRET", "secret"),
        patch.object(s, "KYC_SETU_DIGILOCKER_PRODUCT_ID", "pid"),
    ):
        yield s


async def _mk_admin(session) -> Principal:
    uid = uuid.uuid4()
    await session.execute(
        text("INSERT INTO users (id, full_name, phone) VALUES (:id, 'Admin', :ph)"),
        {"id": str(uid), "ph": "+91973" + uuid.uuid4().hex[:7]},
    )
    await session.commit()
    return Principal(user_id=uid, app_context="admin", roles=("admin",))


@pytest.mark.asyncio
async def test_get_falls_back_to_env_when_unset(
    session, clean_kyc_vendor_setting, both_vendors_configured
):
    admin = await _mk_admin(session)
    resp = await admin_ep.get_kyc_vendor_setting(_p=admin, db=session)
    assert resp.source == "env"
    assert resp.active_vendor == "setu_digilocker"
    assert {v.name: v.configured for v in resp.vendors} == {
        "setu_digilocker": True,
        "apisathi": True,
    }
    assert await active_kyc_vendor_name(session) == "setu_digilocker"


@pytest.mark.asyncio
async def test_switch_to_apisathi_applies_to_new_requests_and_is_audited(
    session, clean_kyc_vendor_setting, both_vendors_configured
):
    admin = await _mk_admin(session)
    resp = await admin_ep.set_kyc_vendor_setting(
        KycVendorUpdate(vendor="apisathi", change_reason="go live on API Sathi"),
        request=_FakeRequest(),
        p=admin,
        db=session,
    )
    await session.commit()
    assert resp.active_vendor == "apisathi"
    assert resp.source == "console"
    assert await active_kyc_vendor_name(session) == "apisathi"

    audit = (
        await session.execute(
            text(
                "SELECT after_json FROM admin_audit_log "
                "WHERE actor_user_id = :uid AND entity_id = :eid"
            ),
            {"uid": str(admin.user_id), "eid": KYC_VENDOR_SETTING_KEY},
        )
    ).scalar_one()
    assert audit == {"vendor": "apisathi"}

    pid = await _seed_pujari(session)
    await session.commit()
    requested: list[str | None] = []

    def _vendor(name=None):
        requested.append(name)
        return _FakeVendor()

    with (
        patch("app.services.partner_kyc_service.get_kyc_vendor", side_effect=_vendor),
        patch.object(kyc_svc.settings, "KYC_REDIRECT_URL", "https://api.example/kyc/callback"),
    ):
        row, _ = await kyc_svc.start_digilocker(session, pujari_id=pid, ip=None, user_agent=None)
    assert row.vendor == "apisathi"
    assert requested == ["apisathi"]


@pytest.mark.asyncio
async def test_switch_back_to_setu(session, clean_kyc_vendor_setting, both_vendors_configured):
    admin = await _mk_admin(session)
    for vendor in ("apisathi", "setu_digilocker"):
        await admin_ep.set_kyc_vendor_setting(
            KycVendorUpdate(vendor=vendor), request=_FakeRequest(), p=admin, db=session
        )
        await session.commit()
    assert await active_kyc_vendor_name(session) == "setu_digilocker"


@pytest.mark.asyncio
async def test_cannot_switch_to_unconfigured_vendor(
    session, clean_kyc_vendor_setting, both_vendors_configured
):
    admin = await _mk_admin(session)
    with (
        patch.object(both_vendors_configured, "KYC_APISATHI_API_KEY", ""),
        pytest.raises(HTTPException) as exc,
    ):
        await admin_ep.set_kyc_vendor_setting(
            KycVendorUpdate(vendor="apisathi"), request=_FakeRequest(), p=admin, db=session
        )
    assert exc.value.status_code == 409
    assert await active_kyc_vendor_name(session) == "setu_digilocker"


@pytest.mark.asyncio
async def test_unknown_vendor_rejected(session, clean_kyc_vendor_setting, both_vendors_configured):
    admin = await _mk_admin(session)
    with pytest.raises(HTTPException) as exc:
        await admin_ep.set_kyc_vendor_setting(
            KycVendorUpdate(vendor="zoop"), request=_FakeRequest(), p=admin, db=session
        )
    assert exc.value.status_code == 422
