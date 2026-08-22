"""Partner DigiLocker KYC flow tests (mocked vendor)."""
from __future__ import annotations

import datetime as dt
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text

from app.api.v1.endpoints import partner_onboarding as onboarding_ep
from app.core.dependencies import Principal
from app.services.kyc_types import KycAadhaarAddress, KycIdentity, KycStartResult, KycStatusResult
from app.services import partner_kyc_service as kyc_svc


async def _seed_pujari(session) -> uuid.UUID:
    uid = uuid.uuid4()
    pid = uuid.uuid4()
    await session.execute(
        text("INSERT INTO users (id, full_name, phone) VALUES (:id, 'Pandit Ram', :ph)"),
        {"id": str(uid), "ph": "+91975" + uuid.uuid4().hex[:7]},
    )
    await session.execute(
        text(
            "INSERT INTO pujaris (id, user_id, verification_status, created_at, updated_at) "
            "VALUES (:pid, :uid, 'pending', now(), now())"
        ),
        {"pid": str(pid), "uid": str(uid)},
    )
    return pid


def _pujari_principal(user_id: uuid.UUID) -> Principal:
    return Principal(user_id=user_id, app_context="pujari", roles=())


class _FakeVendor:
    vendor_name = "setu_digilocker"

    def __init__(self):
        self.revoke = AsyncMock()
        self.status_calls = 0
        self.start_calls = 0

    async def start_digilocker(self, *, redirect_url: str) -> KycStartResult:
        self.start_calls += 1
        vid = f"setu-req-{uuid.uuid4().hex[:12]}"
        return KycStartResult(
            vendor_request_id=vid,
            status="created",
            url="https://digilocker.example/start",
            expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(minutes=30),
        )

    async def get_request_status(self, vendor_request_id: str) -> KycStatusResult:
        self.status_calls += 1
        return KycStatusResult(
            vendor_request_id=vendor_request_id,
            status="authenticated",
            url="https://digilocker.example/start",
            expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(minutes=20),
            scope="ADHAR",
            digilocker_id="DL-test-id",
        )

    async def fetch_aadhaar(self, vendor_request_id: str) -> KycIdentity:
        return KycIdentity(
            name="Pandit Ram",
            date_of_birth="01-01-1990",
            gender="M",
            masked_number="xxxx-xxxx-1234",
            photo_base64=None,
            address=KycAadhaarAddress(
                care_of=None,
                country="India",
                district="Hyderabad",
                house="1",
                landmark=None,
                locality="Loc",
                pin="500001",
                state="Telangana",
                street=None,
                sub_district=None,
                vtc="VTC",
            ),
            xml_file_url=None,
            digilocker_id="DL-test-id",
        )


@pytest.mark.asyncio
async def test_callback_rejects_bad_nonce(session):
    pid = await _seed_pujari(session)
    await session.commit()

    with (
        patch("app.services.partner_kyc_service.get_kyc_vendor", return_value=_FakeVendor()),
        patch.object(kyc_svc.settings, "KYC_REDIRECT_URL", "https://api.example/kyc/callback"),
        patch.object(kyc_svc.settings, "KYC_IDENTITY_PEPPER", "pepper"),
    ):
        row, _ = await kyc_svc.start_digilocker(
            session, pujari_id=pid, ip=None, user_agent=None
        )
    await session.commit()

    with pytest.raises(kyc_svc.PartnerKycError) as exc:
        await kyc_svc.handle_callback(
            session,
            vendor_request_id=row.vendor_request_id,
            success=True,
            nonce="wrong",
            scope="ADHAR",
            error_code=None,
            error_message=None,
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_self_heal_poll_without_callback(session):
    pid = await _seed_pujari(session)
    vendor = _FakeVendor()
    await session.commit()

    with (
        patch("app.services.partner_kyc_service.get_kyc_vendor", return_value=vendor),
        patch.object(kyc_svc.settings, "KYC_REDIRECT_URL", "https://api.example/kyc/callback"),
        patch.object(kyc_svc.settings, "KYC_IDENTITY_PEPPER", "pepper"),
        patch("app.services.kyc_storage.store_kyc_bytes", return_value="key"),
        patch("app.services.partner_kyc_service.redis_set_nx", new_callable=AsyncMock, return_value=True),
        patch("app.services.partner_kyc_service.redis_delete", new_callable=AsyncMock),
    ):
        row, _ = await kyc_svc.start_digilocker(
            session, pujari_id=pid, ip=None, user_agent=None
        )
        await session.commit()

        final_row, created = await kyc_svc.poll_and_finalize(
            session, request_id=row.id, pujari_id=pid
        )
    assert final_row.status == "success"
    assert created == []
    vendor.revoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_public_callback_no_bearer(session):
    pid = await _seed_pujari(session)
    vendor = _FakeVendor()
    nonce = "test-nonce-value"
    with (
        patch("app.services.partner_kyc_service.get_kyc_vendor", return_value=vendor),
        patch("app.services.partner_kyc_service.secrets.token_urlsafe", return_value=nonce),
        patch.object(kyc_svc.settings, "KYC_REDIRECT_URL", "https://api.example/kyc/callback"),
        patch.object(kyc_svc.settings, "KYC_IDENTITY_PEPPER", "pepper"),
        patch.object(kyc_svc.settings, "KYC_APP_RETURN_URL", "managuruji://kyc/complete"),
        patch("app.api.v1.endpoints.partner_onboarding._rate_limit", new_callable=AsyncMock),
    ):
        row, _ = await kyc_svc.start_digilocker(
            session, pujari_id=pid, ip=None, user_agent=None
        )
        await session.commit()

        resp = await onboarding_ep.kyc_callback(
            request=type("R", (), {"client": None, "headers": {}})(),
            id=row.vendor_request_id,
            success=True,
            kyc_nonce=nonce,
            scope="ADHAR",
            errCode=None,
            errMessage=None,
            db=session,
        )
    assert resp.status_code == 302


@pytest.mark.asyncio
async def test_start_resumes_live_request(session):
    pid = await _seed_pujari(session)
    vendor = _FakeVendor()
    await session.commit()
    with (
        patch("app.services.partner_kyc_service.get_kyc_vendor", return_value=vendor),
        patch.object(kyc_svc.settings, "KYC_REDIRECT_URL", "https://api.example/kyc/callback"),
        patch.object(kyc_svc.settings, "KYC_IDENTITY_PEPPER", "pepper"),
    ):
        first, first_url = await kyc_svc.start_digilocker(
            session, pujari_id=pid, ip=None, user_agent=None
        )
        await session.commit()
        second, second_url = await kyc_svc.start_digilocker(
            session, pujari_id=pid, ip=None, user_agent=None
        )
    assert second.id == first.id
    assert second_url
    assert vendor.start_calls == 1
