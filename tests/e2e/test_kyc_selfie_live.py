"""
Live selfie KYC E2E — presign → S3 PUT → confirm (no DigiLocker required).

Prerequisites:
  - uvicorn on :8000 with DEBUG=true (otp_dev_only)
  - S3_BUCKET_KYC + credentials in .env (same as DigiLocker finalize)

Run:

  pytest tests/e2e/test_kyc_selfie_live.py -q -s

CLI (no pytest):

  python tests/e2e/kyc_selfie_smoke.py
  python tests/e2e/kyc_selfie_smoke.py --phone +917675834207
"""
from __future__ import annotations

import sys
from pathlib import Path

_E2E_DIR = Path(__file__).resolve().parent
if str(_E2E_DIR) not in sys.path:
    sys.path.insert(0, str(_E2E_DIR))

import pytest

from kyc_e2e_common import (
    API_BASE,
    EXIF_JPEG,
    MIN_JPEG,
    api_health_ok,
    confirm_selfie,
    fetch_s3_body,
    jpeg_has_exif,
    presign_selfie,
    pujari_session,
    put_selfie,
    require_s3,
    selfie_upload_confirm,
    s3_configured,
)


@pytest.fixture(scope="module")
def api_up():
    if not api_health_ok():
        pytest.skip(f"API not healthy at {API_BASE}/health — start uvicorn first.")


@pytest.fixture(scope="module")
def s3_ready():
    if not s3_configured():
        pytest.skip("Set S3_BUCKET_KYC (+ credentials) in .env for live selfie E2E")


class TestSelfieLiveE2E:
    """Full stack selfie path against running API + real S3."""

    def test_presign_put_confirm_happy_path(self, api_up, s3_ready):
        client, headers, _ = pujari_session()
        try:
            result = selfie_upload_confirm(client, headers)
            assert result["status"] == "pending"
            assert result["file_url"].startswith("kyc/")
            assert "/photo/" in result["file_url"]

            status = client.get(f"{API_BASE}/v1/pujari/kyc/status", headers=headers)
            assert status.status_code == 200, status.text
            photo = next(
                r for r in status.json()["required"] if r["doc_type"] == "photo"
            )
            assert photo["status"] == "pending"
            assert photo["document_id"] == result["document_id"]
        finally:
            client.close()

    def test_confirm_without_upload_returns_422(self, api_up, s3_ready):
        client, headers, _ = pujari_session()
        try:
            presign = presign_selfie(client, headers)
            res = client.post(
                f"{API_BASE}/v1/pujari/documents/{presign['document_id']}/confirm",
                headers=headers,
            )
            assert res.status_code == 422
            assert "upload" in res.text.lower() or "s3" in res.text.lower()
        finally:
            client.close()

    def test_confirm_unknown_document_returns_404(self, api_up, s3_ready):
        client, headers, _ = pujari_session()
        try:
            import uuid

            fake_id = uuid.uuid4()
            res = client.post(
                f"{API_BASE}/v1/pujari/documents/{fake_id}/confirm",
                headers=headers,
            )
            assert res.status_code == 404
        finally:
            client.close()

    def test_exif_stripped_after_confirm(self, api_up, s3_ready):
        assert jpeg_has_exif(EXIF_JPEG)
        client, headers, _ = pujari_session()
        try:
            result = selfie_upload_confirm(
                client, headers, body=EXIF_JPEG, content_type="image/jpeg"
            )
            stored = fetch_s3_body(result["file_url"])
            assert stored.startswith(b"\xff\xd8")
            assert not jpeg_has_exif(stored)
        finally:
            client.close()

    def test_presign_rejects_invalid_content_type(self, api_up, s3_ready):
        client, headers, _ = pujari_session()
        try:
            res = client.post(
                f"{API_BASE}/v1/pujari/documents",
                headers=headers,
                json={"content_type": "application/pdf", "content_length": 100},
            )
            assert res.status_code == 422
        finally:
            client.close()

    def test_second_presign_replaces_current_photo_doc(self, api_up, s3_ready):
        client, headers, _ = pujari_session()
        try:
            first = selfie_upload_confirm(client, headers)
            second = selfie_upload_confirm(client, headers)
            assert first["document_id"] != second["document_id"]

            status = client.get(f"{API_BASE}/v1/pujari/kyc/status", headers=headers)
            photo = next(
                r for r in status.json()["required"] if r["doc_type"] == "photo"
            )
            assert photo["document_id"] == second["document_id"]
        finally:
            client.close()

    def test_put_then_confirm_idempotent_reconfirm(self, api_up, s3_ready):
        """Second confirm on same doc after upload should still succeed."""
        client, headers, _ = pujari_session()
        try:
            presign = presign_selfie(client, headers)
            put_selfie(presign["upload_url"], MIN_JPEG)
            confirm_selfie(client, headers, presign["document_id"])
            again = client.post(
                f"{API_BASE}/v1/pujari/documents/{presign['document_id']}/confirm",
                headers=headers,
            )
            assert again.status_code == 200
            assert again.json()["status"] == "pending"
        finally:
            client.close()
