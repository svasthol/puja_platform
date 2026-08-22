"""KYC S3 path helpers."""
import uuid

from app.services.kyc_storage import kyc_partner_folder


def test_kyc_partner_folder_uses_phone_digits() -> None:
    pid = uuid.uuid4()
    assert kyc_partner_folder("+917675834207", pid) == "917675834207"


def test_kyc_partner_folder_fallback_pujari_id() -> None:
    pid = uuid.uuid4()
    assert kyc_partner_folder(None, pid) == str(pid)
