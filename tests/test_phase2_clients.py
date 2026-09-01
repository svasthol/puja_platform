"""Phase 2 unit tests — MSG91 + FCM HTTP clients (mocked, no vendor keys)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.services.fcm_client import FcmOutcome, send_push_sync
from app.services.msg91_client import normalize_india_mobile, send_otp_sms_sync, send_transactional_sms_sync


class TestNormalizeIndiaMobile:
    def test_ten_digit(self):
        assert normalize_india_mobile("9876543210") == "919876543210"

    def test_e164_plus(self):
        assert normalize_india_mobile("+919876543210") == "919876543210"

    def test_already_prefixed(self):
        assert normalize_india_mobile("919876543210") == "919876543210"


class TestMsg91OtpClient:
    @patch("app.services.msg91_client.settings")
    def test_skips_when_no_auth_key(self, mock_settings):
        mock_settings.MSG91_AUTH_KEY = ""
        mock_settings.MSG91_TEMPLATE_ID = "tpl"
        assert send_otp_sms_sync("+919876543210", "123456") is False

    @patch("app.services.msg91_client.settings")
    @patch("app.services.msg91_client.httpx.Client")
    def test_success_on_msg91_success_type(self, mock_client_cls, mock_settings):
        mock_settings.MSG91_AUTH_KEY = "key"
        mock_settings.MSG91_TEMPLATE_ID = "tpl"
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"type": "success", "message": "3763646c3058373530393938"}
        mock_client_cls.return_value.__enter__.return_value.post.return_value = resp
        assert send_otp_sms_sync("9876543210", "654321") is True
        call_kwargs = mock_client_cls.return_value.__enter__.return_value.post.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params["otp"] == "654321"
        assert params["mobile"] == "919876543210"
        assert params["template_id"] == "tpl"

    @patch("app.services.msg91_client.settings")
    @patch("app.services.msg91_client.httpx.Client")
    def test_failure_on_success_without_request_id(self, mock_client_cls, mock_settings):
        mock_settings.MSG91_AUTH_KEY = "key"
        mock_settings.MSG91_TEMPLATE_ID = "tpl"
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"type": "success", "message": ""}
        mock_client_cls.return_value.__enter__.return_value.post.return_value = resp
        assert send_otp_sms_sync("9876543210", "111111") is False

    @patch("app.services.msg91_client.settings")
    @patch("app.services.msg91_client.httpx.Client")
    def test_failure_on_msg91_error_type(self, mock_client_cls, mock_settings):
        mock_settings.MSG91_AUTH_KEY = "key"
        mock_settings.MSG91_TEMPLATE_ID = "tpl"
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"type": "error", "message": "Invalid template id"}
        mock_client_cls.return_value.__enter__.return_value.post.return_value = resp
        assert send_otp_sms_sync("9876543210", "111111") is False

    @patch("app.services.msg91_client.settings")
    @patch("app.services.msg91_client.httpx.Client")
    def test_failure_on_http_error(self, mock_client_cls, mock_settings):
        mock_settings.MSG91_AUTH_KEY = "key"
        mock_settings.MSG91_TEMPLATE_ID = "tpl"
        mock_client_cls.return_value.__enter__.return_value.post.side_effect = httpx.HTTPError("timeout")
        assert send_otp_sms_sync("9876543210", "111111") is False


class TestMsg91Transactional:
    @patch("app.services.msg91_client.settings")
    @patch("app.services.msg91_client.httpx.Client")
    def test_flow_api_called(self, mock_client_cls, mock_settings):
        mock_settings.MSG91_AUTH_KEY = "key"
        mock_settings.MSG91_TXN_TEMPLATE_ID = "txn_tpl"
        mock_settings.MSG91_TEMPLATE_ID = "otp_tpl"
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        mock_client_cls.return_value.__enter__.return_value.post.return_value = resp
        assert send_transactional_sms_sync("+919876543210", "New offer") is True


class TestFcmClient:
    @patch("app.services.fcm_client.settings")
    def test_skipped_without_credentials(self, mock_settings):
        mock_settings.FCM_SERVICE_ACCOUNT_PATH = ""
        mock_settings.FCM_SERVER_KEY = ""
        result = send_push_sync("tok", title="T", body="B")
        assert result.outcome == FcmOutcome.SKIPPED

    @patch("app.services.fcm_client._access_token", return_value="oauth-token")
    @patch("app.services.fcm_client._load_service_account")
    @patch("app.services.fcm_client._service_account_path")
    @patch("app.services.fcm_client.httpx.Client")
    def test_v1_sent_on_success(
        self, mock_client_cls, mock_path, mock_load_sa, mock_token
    ):
        mock_path.return_value = MagicMock()
        mock_load_sa.return_value = {"project_id": "manapujari"}
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"name": "projects/manapujari/messages/msg-1"}
        mock_client_cls.return_value.__enter__.return_value.post.return_value = resp
        result = send_push_sync("device-tok-abc", title="Offer", body="New job")
        assert result.outcome == FcmOutcome.SENT
        assert result.message_id == "projects/manapujari/messages/msg-1"
        post_call = mock_client_cls.return_value.__enter__.return_value.post.call_args
        url = post_call.args[0]
        assert "/v1/projects/manapujari/messages:send" in url
        payload = post_call.kwargs["json"]["message"]
        assert "notification" in payload
        assert payload["android"]["notification"]["channel_id"] == "mana_guruji_offers_ghanta"
        assert payload["android"]["notification"]["sound"] == "offer_instant_ghanta"

    @patch("app.services.fcm_client._access_token", return_value="oauth-token")
    @patch("app.services.fcm_client._load_service_account")
    @patch("app.services.fcm_client._service_account_path")
    @patch("app.services.fcm_client.httpx.Client")
    def test_v1_advance_offer_is_data_only_silent(
        self, mock_client_cls, mock_path, mock_load_sa, mock_token
    ):
        mock_path.return_value = MagicMock()
        mock_load_sa.return_value = {"project_id": "manapujari"}
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"name": "projects/manapujari/messages/msg-2"}
        mock_client_cls.return_value.__enter__.return_value.post.return_value = resp
        result = send_push_sync(
            "device-tok-adv",
            title="Offer",
            body="Advance inbox",
            priority="normal",
            data={"type": "offer_advance", "booking_id": "b-1"},
        )
        assert result.outcome == FcmOutcome.SENT
        payload = mock_client_cls.return_value.__enter__.return_value.post.call_args.kwargs[
            "json"
        ]["message"]
        assert "notification" not in payload
        android = payload["android"]
        assert "notification" not in android
        assert android["priority"] == "NORMAL"
        assert payload["data"]["type"] == "offer_advance"

    @patch("app.services.fcm_client._access_token", return_value="oauth-token")
    @patch("app.services.fcm_client._load_service_account")
    @patch("app.services.fcm_client._service_account_path")
    @patch("app.services.fcm_client.httpx.Client")
    def test_v1_unregistered(self, mock_client_cls, mock_path, mock_load_sa, mock_token):
        mock_path.return_value = MagicMock()
        mock_load_sa.return_value = {"project_id": "manapujari"}
        resp = MagicMock()
        resp.status_code = 404
        resp.text = "not found"
        resp.json.return_value = {
            "error": {
                "message": "Requested entity was not found.",
                "status": "NOT_FOUND",
                "details": [
                    {
                        "@type": "type.googleapis.com/google.firebase.fcm.v1.FcmError",
                        "errorCode": "UNREGISTERED",
                    }
                ],
            }
        }
        mock_client_cls.return_value.__enter__.return_value.post.return_value = resp
        result = send_push_sync("dead-tok", title="T", body="B", max_attempts=1)
        assert result.outcome == FcmOutcome.UNREGISTERED

    @patch("app.services.fcm_client.settings")
    @patch("app.services.fcm_client.httpx.Client")
    @patch("app.services.fcm_client.time.sleep")
    def test_legacy_retries_transient_failure(self, mock_sleep, mock_client_cls, mock_settings):
        mock_settings.FCM_SERVICE_ACCOUNT_PATH = ""
        mock_settings.FCM_SERVER_KEY = "server-key"
        bad = MagicMock()
        bad.raise_for_status = MagicMock()
        bad.json.return_value = {"success": 0, "results": [{"error": "Unavailable"}]}
        good = MagicMock()
        good.raise_for_status = MagicMock()
        good.json.return_value = {"success": 1, "results": [{"message_id": "ok"}]}
        mock_client_cls.return_value.__enter__.return_value.post.side_effect = [bad, good]
        result = send_push_sync("tok", title="T", body="B", max_attempts=2)
        assert result.outcome == FcmOutcome.SENT
        assert mock_sleep.call_count == 1
