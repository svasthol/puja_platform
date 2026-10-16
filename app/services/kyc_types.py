"""KYC vendor DTOs and Protocol — mirrors sms_types.py."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


class KycVendorError(Exception):
    """Vendor call failed — mapped to 502/500 at the API boundary."""

    def __init__(self, message: str, *, code: str | None = None, retryable: bool = True):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class KycStartResult:
    vendor_request_id: str
    status: str
    url: str
    expires_at: datetime
    scope: str | None = None


@dataclass(frozen=True)
class KycStatusResult:
    vendor_request_id: str
    status: str
    url: str | None
    expires_at: datetime | None
    scope: str | None
    digilocker_id: str | None
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class KycAadhaarAddress:
    care_of: str | None
    country: str | None
    district: str | None
    house: str | None
    landmark: str | None
    locality: str | None
    pin: str | None
    state: str | None
    street: str | None
    sub_district: str | None
    vtc: str | None


@dataclass(frozen=True)
class KycIdentity:
    name: str | None
    date_of_birth: str | None
    gender: str | None
    masked_number: str | None
    photo_base64: str | None
    address: KycAadhaarAddress | None
    xml_file_url: str | None
    digilocker_id: str | None


@dataclass(frozen=True)
class KycWebhookEvent:
    """Dormant — push vendors may implement webhook parsing later."""

    vendor_request_id: str
    status: str
    raw: dict[str, Any]


@dataclass(frozen=True)
class KycPanVerifyResult:
    """Setu POST /api/verify/pan — normalized (no raw PAN in logs)."""

    verification: str  # success | failed
    message: str
    full_name: str | None = None
    category: str | None = None
    trace_id: str | None = None

    @property
    def is_success(self) -> bool:
        return self.verification.lower() == "success"


@runtime_checkable
class KycVendor(Protocol):
    vendor_name: str

    async def start_digilocker(self, *, redirect_url: str) -> KycStartResult: ...

    async def get_request_status(self, vendor_request_id: str) -> KycStatusResult: ...

    async def fetch_aadhaar(self, vendor_request_id: str) -> KycIdentity: ...

    async def revoke(self, vendor_request_id: str) -> None: ...

    def verify_webhook_signature(self, body: bytes, signature: str) -> bool:
        """Optional — dormant until a push vendor is wired."""
        ...

    def parse_webhook(self, payload: dict[str, Any]) -> KycWebhookEvent:
        """Optional — dormant until a push vendor is wired."""
        ...
