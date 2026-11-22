"""Partner DigiLocker KYC flow tests (mocked vendor)."""
from __future__ import annotations

import datetime as dt
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text

from app.api.v1.endpoints import partner_onboarding as onboarding_ep
from app.core.dependencies import Principal
from app.services.kyc_types import (
    KycAadhaarAddress,
    KycIdentity,
    KycStartResult,
    KycStatusResult,
    KycVendorError,
)
from app.services import partner_kyc_service as kyc_svc


async def _seed_pujari(session, *, full_name: str = "Pandit Ram") -> uuid.UUID:
    uid = uuid.uuid4()
    pid = uuid.uuid4()
    await session.execute(
        text("INSERT INTO users (id, full_name, phone) VALUES (:id, :name, :ph)"),
        {"id": str(uid), "name": full_name, "ph": "+91975" + uuid.uuid4().hex[:7]},
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
    supports_resume_url = True

    def __init__(self):
        self.revoke = AsyncMock()
        self.status_calls = 0
        self.start_calls = 0
        self.start_kwargs: dict = {}

    async def start_digilocker(
        self, *, redirect_url: str, reference: str, mobile: str | None = None
    ) -> KycStartResult:
        self.start_calls += 1
        self.start_kwargs = {"redirect_url": redirect_url, "reference": reference, "mobile": mobile}
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
    assert set(created) == {"identity_proof", "address_proof"}
    vendor.revoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_aadhaar_name_replaces_new_user_placeholder(session):
    pid = await _seed_pujari(session, full_name="New User")
    uid = (
        await session.execute(
            text("SELECT user_id FROM pujaris WHERE id = :pid"), {"pid": str(pid)}
        )
    ).scalar_one()
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
        await kyc_svc.poll_and_finalize(session, request_id=row.id, pujari_id=pid)

    name = (
        await session.execute(
            text("SELECT full_name FROM users WHERE id = :uid"), {"uid": str(uid)}
        )
    ).scalar_one()
    assert name == "Pandit Ram"


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
            txnId=None,
            success=True,
            kyc_nonce=nonce,
            scope="ADHAR",
            errCode=None,
            errMessage=None,
            error_code=None,
            errMsg=None,
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


class _AuthenticatedNoUrlVendor(_FakeVendor):
    async def get_request_status(self, vendor_request_id: str) -> KycStatusResult:
        return KycStatusResult(
            vendor_request_id=vendor_request_id,
            status="authenticated",
            url=None,
            expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(minutes=20),
            scope="ADHAR",
            digilocker_id="DL-test-id",
        )


@pytest.mark.asyncio
async def test_resume_authenticated_without_url_poll_only(session):
    pid = await _seed_pujari(session)
    vendor = _FakeVendor()
    await session.commit()
    with (
        patch("app.services.partner_kyc_service.get_kyc_vendor", return_value=vendor),
        patch.object(kyc_svc.settings, "KYC_REDIRECT_URL", "https://api.example/kyc/callback"),
        patch.object(kyc_svc.settings, "KYC_IDENTITY_PEPPER", "pepper"),
    ):
        row, _ = await kyc_svc.start_digilocker(
            session, pujari_id=pid, ip=None, user_agent=None
        )
        await session.commit()

    no_url_vendor = _AuthenticatedNoUrlVendor()
    with patch("app.services.partner_kyc_service.get_kyc_vendor", return_value=no_url_vendor):
        resumed, url = await kyc_svc._resume_or_clear_live(session, row)
    assert resumed is not None
    assert url == ""


@pytest.mark.asyncio
async def test_kyc_status_includes_active_digilocker_request(session):
    pid = await _seed_pujari(session)
    vendor = _FakeVendor()
    await session.commit()
    with (
        patch("app.services.partner_kyc_service.get_kyc_vendor", return_value=vendor),
        patch.object(kyc_svc.settings, "KYC_REDIRECT_URL", "https://api.example/kyc/callback"),
        patch.object(kyc_svc.settings, "KYC_IDENTITY_PEPPER", "pepper"),
    ):
        row, _ = await kyc_svc.start_digilocker(
            session, pujari_id=pid, ip=None, user_agent=None
        )
        await session.commit()
        verification, required, live, _photo_chg = (
            await kyc_svc.get_partner_kyc_status(session, pid)
        )
    assert verification == "pending"
    assert live is not None
    assert live.id == row.id
    assert live.status == "created"
    assert required[0][1] is None


class _FixedTxnVendor(_FakeVendor):
    """Mimics API Sathi TEST keys returning the same OpenAPI example transaction id."""

    vendor_name = "apisathi"
    supports_resume_url = False
    _SHARED_TXN = "873585497344017339"

    async def start_digilocker(
        self, *, redirect_url: str, reference: str, mobile: str | None = None
    ) -> KycStartResult:
        self.start_calls += 1
        self.start_kwargs = {"redirect_url": redirect_url, "reference": reference, "mobile": mobile}
        return KycStartResult(
            vendor_request_id=self._SHARED_TXN,
            status="created",
            url="https://digilocker.example/start",
            expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(minutes=30),
        )


class _ApiSathiLikeVendor(_FakeVendor):
    """No DigiLocker id, no resume URL — identity comes from the Aadhaar record only."""

    vendor_name = "apisathi"
    supports_resume_url = False

    def __init__(self, *, name: str, dob: str = "1990-04-12", masked: str = "XXXXXXXX4321"):
        super().__init__()
        self._name = name
        self._dob = dob
        self._masked = masked

    async def get_request_status(self, vendor_request_id: str) -> KycStatusResult:
        self.status_calls += 1
        return KycStatusResult(
            vendor_request_id=vendor_request_id,
            status="authenticated",
            url=None,
            expires_at=None,
            scope="ADHAR",
            digilocker_id=None,
        )

    async def fetch_aadhaar(self, vendor_request_id: str) -> KycIdentity:
        return KycIdentity(
            name=self._name,
            date_of_birth=self._dob,
            gender="M",
            masked_number=self._masked,
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
            digilocker_id=None,
        )


def _finalize_patches(vendor):
    return (
        patch("app.services.partner_kyc_service.get_kyc_vendor", return_value=vendor),
        patch.object(kyc_svc.settings, "KYC_REDIRECT_URL", "https://api.example/kyc/callback"),
        patch.object(kyc_svc.settings, "KYC_IDENTITY_PEPPER", "pepper"),
        patch("app.services.partner_kyc_service.redis_set_nx", new_callable=AsyncMock, return_value=True),
        patch("app.services.partner_kyc_service.redis_delete", new_callable=AsyncMock),
    )


async def _run_kyc(session, pid, vendor):
    p1, p2, p3, p4, p5 = _finalize_patches(vendor)
    with p1, p2, p3, p4, p5:
        row, _ = await kyc_svc.start_digilocker(session, pujari_id=pid, ip=None, user_agent=None)
        await session.commit()
        final_row, _ = await kyc_svc.poll_and_finalize(session, request_id=row.id, pujari_id=pid)
        await session.commit()
    return final_row


@pytest.mark.asyncio
async def test_apisathi_test_key_allows_retry_after_success_despite_shared_txn(session):
    pid = await _seed_pujari(session)
    vendor = _FixedTxnVendor()
    await session.commit()
    p1, p2, p3, _p4, _p5 = _finalize_patches(vendor)
    with (
        p1,
        p2,
        p3,
        patch.object(kyc_svc.settings, "KYC_APISATHI_API_KEY", "test_wus2NDheHKmMttjt"),
    ):
        first, _ = await kyc_svc.start_digilocker(session, pujari_id=pid, ip=None, user_agent=None)
        await session.execute(
            text(
                "UPDATE kyc_verification_requests SET status = 'success' WHERE id = :id"
            ),
            {"id": str(first.id)},
        )
        await session.commit()
        second, _ = await kyc_svc.start_digilocker(session, pujari_id=pid, ip=None, user_agent=None)
        await session.commit()
    assert first.vendor_request_id == f"{_FixedTxnVendor._SHARED_TXN}::{first.id}"
    assert second.vendor_request_id == f"{_FixedTxnVendor._SHARED_TXN}::{second.id}"
    assert first.vendor_request_id != second.vendor_request_id


@pytest.mark.asyncio
async def test_start_passes_reference_and_mobile_to_vendor(session):
    pid = await _seed_pujari(session)
    vendor = _FakeVendor()
    await session.commit()
    p1, p2, p3, _p4, _p5 = _finalize_patches(vendor)
    with p1, p2, p3:
        row, _ = await kyc_svc.start_digilocker(session, pujari_id=pid, ip=None, user_agent=None)
    assert vendor.start_kwargs["reference"] == str(row.id)
    assert vendor.start_kwargs["mobile"].startswith("+91975")
    assert "kyc_nonce=" in vendor.start_kwargs["redirect_url"]


@pytest.mark.asyncio
async def test_duplicate_aadhaar_is_flagged_not_blocked(session):
    unique_name = f"Pandit Dup {uuid.uuid4().hex[:8]}"
    first_pid = await _seed_pujari(session, full_name=unique_name)
    second_pid = await _seed_pujari(session, full_name=unique_name)
    await session.commit()

    first = await _run_kyc(session, first_pid, _ApiSathiLikeVendor(name=unique_name))
    second = await _run_kyc(session, second_pid, _ApiSathiLikeVendor(name=unique_name))

    assert first.status == "success"
    assert "duplicate_identity" not in first.review_flags
    assert second.status == "success"
    assert "duplicate_identity" in second.review_flags
    assert kyc_svc.partner_visible_review_flags(second.review_flags) == []


@pytest.mark.asyncio
async def test_denied_identity_is_flagged_for_admin(session):
    unique_name = f"Pandit Denied {uuid.uuid4().hex[:8]}"
    first_pid = await _seed_pujari(session, full_name=unique_name)
    await session.commit()
    await _run_kyc(session, first_pid, _ApiSathiLikeVendor(name=unique_name))
    admin_user_id = (
        await session.execute(
            text("SELECT user_id FROM pujaris WHERE id = :pid"), {"pid": str(first_pid)}
        )
    ).scalar_one()
    with patch.object(kyc_svc.settings, "KYC_IDENTITY_PEPPER", "pepper"):
        await kyc_svc.deny_identity(
            session,
            actor_user_id=admin_user_id,
            denied_reason="fraud",
            digilocker_id_hash=None,
            pujari_id=first_pid,
        )
    await session.commit()

    retry_pid = await _seed_pujari(session, full_name=unique_name)
    await session.commit()
    retry = await _run_kyc(session, retry_pid, _ApiSathiLikeVendor(name=unique_name))
    assert retry.status == "success"
    assert "identity_blocked" in retry.review_flags
    assert kyc_svc.partner_visible_review_flags(retry.review_flags) == []


@pytest.mark.asyncio
async def test_identity_check_unavailable_when_aadhaar_incomplete(session):
    pid = await _seed_pujari(session)
    await session.commit()
    row = await _run_kyc(session, pid, _ApiSathiLikeVendor(name="Pandit Ram", masked=""))
    assert row.status == "success"
    assert "identity_check_unavailable" in row.review_flags


def test_demographic_key_is_stable_across_formats():
    a = KycIdentity(
        name="RAHUL  VERMA", date_of_birth="12-04-1990", gender="M",
        masked_number="xxxx-xxxx-1234", photo_base64=None, address=None,
        xml_file_url=None, digilocker_id=None,
    )
    b = KycIdentity(
        name="Rahul Verma", date_of_birth="1990-04-12", gender="M",
        masked_number="XXXXXXXX1234", photo_base64=None, address=None,
        xml_file_url=None, digilocker_id=None,
    )
    assert kyc_svc._aadhaar_demographic_key(a) == kyc_svc._aadhaar_demographic_key(b)
    assert kyc_svc._aadhaar_demographic_key(a).startswith("aadhaar-demographic-v1|")


class _PendingNoUrlVendor(_ApiSathiLikeVendor):
    async def get_request_status(self, vendor_request_id: str) -> KycStatusResult:
        return KycStatusResult(
            vendor_request_id=vendor_request_id,
            status="created",
            url=None,
            expires_at=None,
            scope=None,
            digilocker_id=None,
        )


@pytest.mark.asyncio
async def test_apisathi_resume_pending_does_not_start_second_init(session):
    """API Sathi pending (created, no URL) must not expire the row or call init again."""
    pid = await _seed_pujari(session)
    vendor = _PendingNoUrlVendor(name="Pandit Ram")
    await session.commit()
    p1, p2, p3, _p4, _p5 = _finalize_patches(vendor)
    with (
        p1,
        p2,
        p3,
        patch.object(kyc_svc.settings, "KYC_VENDOR_STATUS_POLL_MIN_SECONDS", 0),
    ):
        first, first_url = await kyc_svc.start_digilocker(
            session, pujari_id=pid, ip=None, user_agent=None
        )
        await session.commit()
        second, second_url = await kyc_svc.start_digilocker(
            session, pujari_id=pid, ip=None, user_agent=None
        )
        await session.commit()
    assert second.id == first.id
    assert vendor.start_calls == 1
    assert first_url
    assert second_url == ""


class _SetuCreatedNoUrlVendor(_FakeVendor):
    supports_resume_url = True

    async def get_request_status(self, vendor_request_id: str) -> KycStatusResult:
        return KycStatusResult(
            vendor_request_id=vendor_request_id,
            status="created",
            url=None,
            expires_at=None,
            scope=None,
            digilocker_id=None,
        )


@pytest.mark.asyncio
async def test_setu_reissues_link_when_created_without_url(session):
    pid = await _seed_pujari(session)
    vendor = _SetuCreatedNoUrlVendor()
    await session.commit()
    p1, p2, p3, _p4, _p5 = _finalize_patches(vendor)
    with (
        p1,
        p2,
        p3,
        patch.object(kyc_svc.settings, "KYC_VENDOR_STATUS_POLL_MIN_SECONDS", 0),
    ):
        first, _ = await kyc_svc.start_digilocker(
            session, pujari_id=pid, ip=None, user_agent=None
        )
        await session.commit()
        second, second_url = await kyc_svc.start_digilocker(
            session, pujari_id=pid, ip=None, user_agent=None
        )
        await session.commit()
    assert second.id != first.id
    assert second_url
    assert vendor.start_calls == 2


@pytest.mark.asyncio
async def test_public_callback_bad_nonce_still_returns_to_app(session):
    pid = await _seed_pujari(session)
    vendor = _FakeVendor()
    with (
        patch("app.services.partner_kyc_service.get_kyc_vendor", return_value=vendor),
        patch.object(kyc_svc.settings, "KYC_REDIRECT_URL", "https://api.example/kyc/callback"),
        patch.object(kyc_svc.settings, "KYC_IDENTITY_PEPPER", "pepper"),
        patch.object(kyc_svc.settings, "KYC_APP_RETURN_URL", "managuruji://kyc/complete"),
        patch("app.api.v1.endpoints.partner_onboarding._rate_limit", new_callable=AsyncMock),
    ):
        row, _ = await kyc_svc.start_digilocker(session, pujari_id=pid, ip=None, user_agent=None)
        await session.commit()
        resp = await onboarding_ep.kyc_callback(
            request=type("R", (), {"client": None, "headers": {}})(),
            id=None,
            txnId=row.vendor_request_id,
            success=None,
            kyc_nonce=None,
            scope=None,
            errCode=None,
            errMessage=None,
            error_code="DG1001",
            errMsg="User declined consent",
            db=session,
        )
    assert resp.status_code == 302
    await session.refresh(row)
    assert row.status == "created"


class _PanVendor(_FakeVendor):
    vendor_name = "apisathi"

    def __init__(self, *, result=None, error=None):
        super().__init__()
        self.pan_calls: list[str] = []
        self._result = result
        self._error = error

    def pan_verification_enabled(self) -> bool:
        return True

    async def verify_pan(self, *, pan: str, consent: bool, reason: str):
        self.pan_calls.append(pan)
        if self._error is not None:
            raise self._error
        return self._result


@pytest.mark.asyncio
async def test_submit_pan_routes_through_configured_vendor(session):
    from app.services import pujari_compliance
    from app.services.kyc_types import KycPanVerifyResult

    pid = await _seed_pujari(session)
    await session.commit()
    vendor = _PanVendor(
        result=KycPanVerifyResult(verification="success", message="ok", full_name="Pandit Ram")
    )
    with patch("app.services.pujari_compliance.get_kyc_vendor", return_value=vendor):
        out = await pujari_compliance.submit_partner_pan(
            session,
            pujari_id=pid,
            entity_type="individual",
            pan="abcpe1234f",
            consent=True,
            reason="TDS compliance verification for partner onboarding",
        )
    assert vendor.pan_calls == ["ABCPE1234F"]
    assert out["pan_status"] == "operative"
    assert out["verified_name"] == "Pandit Ram"


@pytest.mark.asyncio
async def test_submit_pan_wallet_empty_is_503_not_user_error(session):
    from fastapi import HTTPException

    from app.services import pujari_compliance
    from app.services.kyc_types import KycVendorError

    pid = await _seed_pujari(session)
    await session.commit()
    vendor = _PanVendor(
        error=KycVendorError("wallet low", code="insufficient_balance", retryable=False)
    )
    with (
        patch("app.services.pujari_compliance.get_kyc_vendor", return_value=vendor),
        pytest.raises(HTTPException) as exc,
    ):
        await pujari_compliance.submit_partner_pan(
            session,
            pujari_id=pid,
            entity_type="individual",
            pan="ABCPE1234F",
            consent=True,
            reason="TDS compliance verification for partner onboarding",
        )
    assert exc.value.status_code == 503
    assert "wallet" not in str(exc.value.detail).lower()


class _RateLimitedVendor(_FakeVendor):
    async def get_request_status(self, vendor_request_id: str) -> KycStatusResult:
        raise KycVendorError(
            "API Sathi upstream error 429",
            code="rate_limited",
            retryable=True,
        )


@pytest.mark.asyncio
async def test_poll_throttled_skips_vendor_status_call(session):
    """Redis poll slot must short-circuit before any vendor HTTP call."""
    pid = await _seed_pujari(session)
    vendor = _FakeVendor()
    vendor.get_request_status = AsyncMock(
        return_value=KycStatusResult(
            vendor_request_id="411239325508312066",
            status="created",
            url=None,
            expires_at=None,
            scope=None,
            digilocker_id=None,
        )
    )
    await session.commit()

    poll_slots = [True, False]

    async def _redis_nx(key: str, value: str, *, ex: int) -> bool:
        if key.startswith("kyc:vendor_poll:"):
            return poll_slots.pop(0) if poll_slots else False
        return True

    with (
        patch("app.services.partner_kyc_service.get_kyc_vendor", return_value=vendor),
        patch.object(kyc_svc.settings, "KYC_REDIRECT_URL", "https://api.example/kyc/callback"),
        patch.object(kyc_svc.settings, "KYC_IDENTITY_PEPPER", "pepper"),
        patch.object(kyc_svc.settings, "KYC_VENDOR_STATUS_POLL_MIN_SECONDS", 15),
        patch("app.services.partner_kyc_service.redis_set_nx", side_effect=_redis_nx),
        patch("app.services.partner_kyc_service.redis_delete", new_callable=AsyncMock),
    ):
        row, _ = await kyc_svc.start_digilocker(
            session, pujari_id=pid, ip=None, user_agent=None
        )
        await session.commit()
        await kyc_svc.poll_and_finalize(session, request_id=row.id, pujari_id=pid)
        await session.commit()
        await kyc_svc.poll_and_finalize(session, request_id=row.id, pujari_id=pid)

    assert vendor.get_request_status.await_count == 1


@pytest.mark.asyncio
async def test_poll_deferred_on_retryable_vendor_error(session):
    """Status poll must stay 200/created while vendor is rate-limited — not 502."""
    pid = await _seed_pujari(session)
    vendor = _RateLimitedVendor()
    await session.commit()

    with (
        patch("app.services.partner_kyc_service.get_kyc_vendor", return_value=vendor),
        patch.object(kyc_svc.settings, "KYC_REDIRECT_URL", "https://api.example/kyc/callback"),
        patch.object(kyc_svc.settings, "KYC_IDENTITY_PEPPER", "pepper"),
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

    assert final_row.status == "created"
    assert created == []


@pytest.mark.asyncio
async def test_download_url_rejects_non_https():
    with pytest.raises(ValueError, match="HTTPS"):
        await kyc_svc._download_url("http://vendor.example/doc.pdf")


@pytest.mark.asyncio
async def test_download_url_rejects_private_host():
    with pytest.raises(ValueError, match="not allowed"):
        await kyc_svc._download_url("https://127.0.0.1/doc.pdf")


@pytest.mark.asyncio
async def test_download_url_streams_with_size_cap():
    body = b"x" * 64

    class _Resp:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def raise_for_status(self):
            return None

        async def aiter_bytes(self):
            yield body

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def stream(self, method, url):
            assert method == "GET"
            assert url.startswith("https://")
            return _Resp()

    with (
        patch.object(kyc_svc.settings, "S3_KYC_MAX_BYTES", 32),
        patch("app.services.partner_kyc_service.httpx.AsyncClient", return_value=_Client()),
    ):
        with pytest.raises(ValueError, match="size limit"):
            await kyc_svc._download_url("https://files.vendor.example/aadhaar.xml")
