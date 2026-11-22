"""API Sathi KYC client — request shape + response mapping (httpx MockTransport, no network)."""
from __future__ import annotations

import json
from unittest.mock import patch

import httpx
import pytest

from app.services import apisathi_kyc_client as mod
from app.services.apisathi_kyc_client import (
    ApiSathiKycClient,
    is_placeholder_kyc_url,
    normalize_indian_mobile,
    storage_vendor_request_id,
    vendor_txn_for_api,
)
from app.services.kyc_types import KycVendor, KycVendorError

_TXN = "873585497344017339"

_VERIFIED_FETCH = {
    "verified": True,
    "status": "s",
    "masked_aadhaar": "XXXXXXXX1234",
    "name": "RAHUL VERMA",
    "dob": "1990-04-12",
    "gender": "M",
    "care_of": "S/O Ram Verma",
    "address": {"house": "12", "street": "MG Road", "dist": "Jaipur", "state": "Rajasthan", "pc": "302001"},
    "photo_base64": "data:image/jpeg;base64,/9j/AAAA",
    "documents": [
        {"docType": "ADHAR", "docExtension": "pdf", "docLink": "https://files.example/a.pdf"},
        {"docType": "ADHAR", "docExtension": "xml", "docLink": "https://files.example/a.xml"},
    ],
}


def _mock_client(handler):
    real = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    return patch.object(mod.httpx, "AsyncClient", lambda **kw: real(transport=transport, **kw))


@pytest.fixture(autouse=True)
def _apisathi_settings():
    settings = mod.get_settings()
    with (
        patch.object(settings, "KYC_APISATHI_API_KEY", "test_key_123"),
        patch.object(settings, "KYC_APISATHI_BASE_URL", "https://apisathi.in/gw/v1"),
        patch.object(settings, "KYC_REQUEST_TTL_MINUTES", 30),
    ):
        yield


def _err(status: int, code: str, message: str) -> httpx.Response:
    return httpx.Response(status, json={"error": {"code": code, "message": message, "call_id": "c1"}})


def test_client_implements_protocol():
    assert isinstance(ApiSathiKycClient(), KycVendor)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+919876543210", "9876543210"),
        ("919876543210", "9876543210"),
        ("09876543210", "9876543210"),
        ("9876543210", "9876543210"),
        ("+915876543210", None),
        ("", None),
        (None, None),
    ],
)
def test_normalize_indian_mobile(raw, expected):
    assert normalize_indian_mobile(raw) == expected


def test_vendor_txn_for_api_strips_test_storage_suffix():
    rid = "33356a0b-2e5b-4f49-9ada-d12c6b7074bd"
    stored = f"{_TXN}::{rid}"
    assert vendor_txn_for_api(stored) == _TXN
    assert vendor_txn_for_api(_TXN) == _TXN


@pytest.mark.parametrize(
    ("url", "placeholder"),
    [
        ("https://digilocker.example/?token=x", True),
        ("https://smler.example/UA1UhGHvwi", True),
        ("https://digilocker.meripehchaan.gov.in/", False),
        ("", False),
    ],
)
def test_is_placeholder_kyc_url(url, placeholder):
    assert is_placeholder_kyc_url(url) is placeholder


def test_storage_vendor_request_id_namespaces_test_keys_only():
    rid = "33356a0b-2e5b-4f49-9ada-d12c6b7074bd"
    assert storage_vendor_request_id(_TXN, request_id=rid) == f"{_TXN}::{rid}"
    with patch.object(mod, "_api_key", return_value="live_prod_key"):
        assert storage_vendor_request_id(_TXN, request_id=rid) == _TXN


@pytest.mark.asyncio
async def test_start_sends_documented_body_and_maps_result():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("X-API-Key")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"verified": True, "transaction_id": _TXN, "kyc_url": "https://dl.example/x", "short_url": "s"},
        )

    with _mock_client(handler):
        result = await ApiSathiKycClient().start_digilocker(
            redirect_url="https://api.example/v1/pujari/kyc/callback?kyc_nonce=n1",
            reference="0b6b7c1e-1111-2222-3333-444455556666",
            mobile="+919876543210",
        )

    assert seen["url"] == "https://apisathi.in/gw/v1/aadhaar-digilocker-init-v1/"
    assert seen["key"] == "test_key_123"
    assert seen["body"] == {
        "uid": "0b6b7c1e-1111-2222-3333-444455556666",
        "mobile": "9876543210",
        "redirectionUrl": "https://api.example/v1/pujari/kyc/callback?kyc_nonce=n1",
    }
    assert result.vendor_request_id == _TXN
    assert result.url == ""
    assert result.status == "created"
    assert result.expires_at is not None


@pytest.mark.asyncio
async def test_start_rejects_missing_mobile_without_calling_vendor():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("vendor must not be called")

    with _mock_client(handler), pytest.raises(KycVendorError) as exc:
        await ApiSathiKycClient().start_digilocker(
            redirect_url="https://api.example/cb", reference="r1", mobile=None
        )
    assert exc.value.code == "invalid_mobile"


@pytest.mark.asyncio
async def test_status_pending_422_maps_to_created():
    def handler(request: httpx.Request) -> httpx.Response:
        return _err(422, "INVALID_INPUT", "The given transaction id for digilocker is not success")

    with _mock_client(handler):
        status = await ApiSathiKycClient().get_request_status(_TXN)
    assert status.status == "created"
    assert status.url is None


@pytest.mark.asyncio
async def test_status_duplicate_throttle_422_maps_to_created():
    def handler(request: httpx.Request) -> httpx.Response:
        return _err(422, "DUPLICATE_REQUEST_THROTTLED", "Duplicate fetch; try again later")

    with _mock_client(handler):
        status = await ApiSathiKycClient().get_request_status(_TXN)
    assert status.status == "created"


@pytest.mark.asyncio
async def test_status_customer_decline_maps_to_failed():
    def handler(request: httpx.Request) -> httpx.Response:
        return _err(422, "DG1001", "User declined consent")

    with _mock_client(handler):
        status = await ApiSathiKycClient().get_request_status(_TXN)
    assert status.status == "failed"
    assert status.error_code == "DG1001"


@pytest.mark.asyncio
async def test_status_404_raises_request_not_found():
    def handler(request: httpx.Request) -> httpx.Response:
        return _err(404, "NOT_FOUND", "No verification with that id")

    with _mock_client(handler), pytest.raises(KycVendorError) as exc:
        await ApiSathiKycClient().get_request_status(_TXN)
    assert exc.value.code == "request_not_found"


@pytest.mark.asyncio
async def test_verified_fetch_is_billed_once_per_finalize():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        assert json.loads(request.content) == {"transaction_id": _TXN}
        return httpx.Response(200, json=_VERIFIED_FETCH)

    client = ApiSathiKycClient()
    with _mock_client(handler):
        status = await client.get_request_status(_TXN)
        identity = await client.fetch_aadhaar(_TXN)

    assert calls["n"] == 1
    assert status.status == "authenticated"
    assert status.scope == "ADHAR"
    assert status.digilocker_id is None
    assert identity.name == "RAHUL VERMA"
    assert identity.date_of_birth == "1990-04-12"
    assert identity.masked_number == "XXXXXXXX1234"
    assert identity.photo_base64 == "/9j/AAAA"
    assert identity.xml_file_url == "https://files.example/a.xml"
    assert identity.address is not None
    assert identity.address.district == "Jaipur"
    assert identity.address.pin == "302001"
    assert identity.address.care_of == "S/O Ram Verma"


@pytest.mark.asyncio
async def test_fetch_aadhaar_while_pending_raises_not_ready():
    def handler(request: httpx.Request) -> httpx.Response:
        return _err(422, "INVALID_INPUT", "The given transaction id for digilocker is not success")

    with _mock_client(handler), pytest.raises(KycVendorError) as exc:
        await ApiSathiKycClient().fetch_aadhaar(_TXN)
    assert exc.value.code == "not_ready"


@pytest.mark.parametrize(
    ("status", "code"),
    [(401, "vendor_auth"), (403, "vendor_auth"), (402, "insufficient_balance"), (410, "product_retired")],
)
@pytest.mark.asyncio
async def test_account_errors_are_not_retryable(status, code):
    def handler(request: httpx.Request) -> httpx.Response:
        return _err(status, "X", "x")

    with _mock_client(handler), pytest.raises(KycVendorError) as exc:
        await ApiSathiKycClient().get_request_status(_TXN)
    assert exc.value.code == code
    assert exc.value.retryable is False


@pytest.mark.parametrize("status", [429, 502, 503, 504])
@pytest.mark.asyncio
async def test_transient_errors_are_retryable(status):
    def handler(request: httpx.Request) -> httpx.Response:
        return _err(status, "X", "x")

    with _mock_client(handler), pytest.raises(KycVendorError) as exc:
        await ApiSathiKycClient().get_request_status(_TXN)
    assert exc.value.retryable is True


@pytest.mark.asyncio
async def test_verify_pan_success_sends_only_pan():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"verified": True, "name": "Rohit Sharma", "category": "Individual", "dob": "1990-01-15"},
        )

    with _mock_client(handler):
        result = await ApiSathiKycClient().verify_pan(
            pan="abcpe1234f", consent=True, reason="TDS compliance verification for partner onboarding"
        )
    assert seen["url"] == "https://apisathi.in/gw/v1/pan-verification-v1/"
    assert seen["body"] == {"pan": "ABCPE1234F"}
    assert result.is_success
    assert result.full_name == "Rohit Sharma"


@pytest.mark.asyncio
async def test_verify_pan_no_record_is_failed_result():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"verified": False})

    with _mock_client(handler):
        result = await ApiSathiKycClient().verify_pan(pan="ABCPE1234F", consent=True, reason="x" * 20)
    assert not result.is_success


@pytest.mark.asyncio
async def test_verify_pan_invalid_input_maps_to_pan_not_found():
    def handler(request: httpx.Request) -> httpx.Response:
        return _err(422, "INVALID_INPUT", "Invalid PAN")

    with _mock_client(handler), pytest.raises(KycVendorError) as exc:
        await ApiSathiKycClient().verify_pan(pan="ABCDE1234F", consent=True, reason="x" * 20)
    assert exc.value.code == "pan_not_found"


def test_pan_verification_enabled_follows_api_key():
    settings = mod.get_settings()
    client = ApiSathiKycClient()
    assert client.pan_verification_enabled() is True
    with patch.object(settings, "KYC_APISATHI_API_KEY", ""):
        assert client.pan_verification_enabled() is False
