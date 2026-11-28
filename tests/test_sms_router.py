"""SMS router + FAST2SMS client tests — failover without live vendor keys."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services import sms_router
from app.services.fast2sms_client import send_otp_sms_sync, send_transactional_sms_sync
from app.services.sms_phone import normalize_india_mobile_ten


def _mock_fast2sms_settings(**overrides):
    from types import SimpleNamespace

    base = {
        "FAST2SMS_API_KEY": "",
        "FAST2SMS_SENDER_ID": "MNGURU",
        "FAST2SMS_OTP_ROUTE": "otp",
        "FAST2SMS_QUICK_ROUTE": "q",
        "FAST2SMS_DLT_OTP_MESSAGE_ID": "",
        "FAST2SMS_DLT_BOOKING_MESSAGE_ID": "",
        "FAST2SMS_DLT_ENTITY_ID": "",
        "FAST2SMS_DLT_OTP_TEMPLATE_ID": "",
        "FAST2SMS_DLT_BOOKING_TEMPLATE_ID": "",
        "OTP_EXPIRE_MINUTES": 5,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class TestFast2SmsClient:
    @patch("app.services.sms_dlt.get_settings")
    @patch("app.services.fast2sms_client.get_settings")
    def test_skips_without_api_key(self, mock_f2s, mock_dlt):
        cfg = _mock_fast2sms_settings()
        mock_f2s.return_value = cfg
        mock_dlt.return_value = cfg
        assert send_otp_sms_sync("+919876543210", "123456") is False

    @patch("app.services.sms_dlt.get_settings")
    @patch("app.services.fast2sms_client.get_settings")
    @patch("app.services.fast2sms_client.httpx.Client")
    def test_otp_legacy_route_without_dlt(self, mock_client_cls, mock_f2s, mock_dlt):
        cfg = _mock_fast2sms_settings(FAST2SMS_API_KEY="f2s-key")
        mock_f2s.return_value = cfg
        mock_dlt.return_value = cfg
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"return": True, "request_id": "abc123"}
        mock_client_cls.return_value.__enter__.return_value.post.return_value = resp
        assert send_otp_sms_sync("9876543210", "654321") is True
        call = mock_client_cls.return_value.__enter__.return_value.post.call_args
        payload = call.kwargs.get("data") or call[1].get("data")
        assert payload["numbers"] == "9876543210"
        assert payload["variables_values"] == "654321"
        assert payload["route"] == "otp"

    @patch("app.services.sms_dlt.get_settings")
    @patch("app.services.fast2sms_client.get_settings")
    @patch("app.services.fast2sms_client.httpx.Client")
    def test_otp_dlt_route_with_message_id(self, mock_client_cls, mock_f2s, mock_dlt):
        cfg = _mock_fast2sms_settings(
            FAST2SMS_API_KEY="f2s-key",
            FAST2SMS_DLT_OTP_MESSAGE_ID="40003",
        )
        mock_f2s.return_value = cfg
        mock_dlt.return_value = cfg
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"return": True, "request_id": "dlt1"}
        mock_client_cls.return_value.__enter__.return_value.post.return_value = resp
        assert send_otp_sms_sync("9876543210", "654321") is True
        payload = mock_client_cls.return_value.__enter__.return_value.post.call_args.kwargs.get(
            "data"
        ) or mock_client_cls.return_value.__enter__.return_value.post.call_args[1]["data"]
        assert payload["route"] == "dlt"
        assert payload["sender_id"] == "MNGURU"
        assert payload["message"] == "40003"
        assert payload["variables_values"] == "654321"

    @patch("app.services.sms_dlt.get_settings")
    @patch("app.services.fast2sms_client.get_settings")
    @patch("app.services.fast2sms_client.httpx.Client")
    def test_booking_dlt_manual(self, mock_client_cls, mock_f2s, mock_dlt):
        from app.services.fast2sms_client import send_booking_confirmed_sms_sync

        cfg = _mock_fast2sms_settings(
            FAST2SMS_API_KEY="f2s-key",
            FAST2SMS_DLT_ENTITY_ID="1701158987654321098",
        )
        mock_f2s.return_value = cfg
        mock_dlt.return_value = cfg
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"return": True}
        mock_client_cls.return_value.__enter__.return_value.post.return_value = resp
        ok = send_booking_confirmed_sms_sync(
            "9876543210",
            puja_name="Satyanarayana puja",
            scheduled_date=__import__("datetime").date(2026, 11, 28),
            scheduled_time=__import__("datetime").time(7, 30),
            booking_id="abcd0000-0000-0000-0000-000000000001",
        )
        assert ok is True
        payload = mock_client_cls.return_value.__enter__.return_value.post.call_args[1]["data"]
        assert payload["route"] == "dlt_manual"
        assert "Satyanarayana puja" in payload["message"]
        assert "Ref ABCD0000" in payload["message"]

    @patch("app.services.sms_dlt.get_settings")
    @patch("app.services.fast2sms_client.get_settings")
    @patch("app.services.fast2sms_client.httpx.Client")
    def test_txn_quick_route(self, mock_client_cls, mock_f2s, mock_dlt):
        cfg = _mock_fast2sms_settings(FAST2SMS_API_KEY="f2s-key")
        mock_f2s.return_value = cfg
        mock_dlt.return_value = cfg
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"return": True}
        mock_client_cls.return_value.__enter__.return_value.post.return_value = resp
        assert send_transactional_sms_sync("+919876543210", "New offer") is True


class TestSmsRouterFailover:
    @patch("app.services.sms_router.settings")
    @patch("app.services.sms_router.fast2sms_client.send_otp_sms_sync", return_value=False)
    @patch("app.services.sms_router.msg91_client.send_otp_sms_sync", return_value=True)
    def test_failover_to_msg91_when_fast2sms_fails(self, _m91, _f2s, mock_settings):
        mock_settings.SMS_PROVIDER_ORDER = "fast2sms,msg91"
        mock_settings.MSG91_ENABLED = True
        result = sms_router.send_otp_sms_sync("+919876543210", "111111")
        assert result.sent is True
        assert result.provider == "msg91"

    @patch("app.services.sms_router.settings")
    @patch("app.services.sms_router.fast2sms_client.send_otp_sms_sync", return_value=True)
    @patch("app.services.sms_router.msg91_client.send_otp_sms_sync")
    def test_fast2sms_wins_first(self, mock_m91, _f2s, mock_settings):
        mock_settings.SMS_PROVIDER_ORDER = "fast2sms,msg91"
        mock_settings.MSG91_ENABLED = True
        result = sms_router.send_otp_sms_sync("+919876543210", "222222")
        assert result.sent is True
        assert result.provider == "fast2sms"
        mock_m91.assert_not_called()

    @patch("app.services.sms_router.settings")
    @patch("app.services.sms_router.msg91_client.send_otp_sms_sync")
    @patch("app.services.sms_router.fast2sms_client.send_otp_sms_sync", return_value=False)
    def test_msg91_skipped_when_disabled(self, _f2s, mock_m91, mock_settings):
        mock_settings.SMS_PROVIDER_ORDER = "fast2sms,msg91"
        mock_settings.MSG91_ENABLED = False
        result = sms_router.send_otp_sms_sync("+919876543210", "333333")
        assert result.sent is False
        mock_m91.assert_not_called()

    @patch("app.services.sms_router.settings")
    @patch("app.services.sms_router.fast2sms_client.send_transactional_sms_sync", return_value=True)
    def test_txn_uses_router(self, _f2s, mock_settings):
        mock_settings.SMS_PROVIDER_ORDER = "fast2sms"
        assert sms_router.send_transactional_sms_sync("+919876543210", "hello") is True


class TestPhoneNormalize:
    def test_ten_digit_from_e164(self):
        assert normalize_india_mobile_ten("+919876543210") == "9876543210"
