"""DLT template builders and variable hygiene (Jio-approved Mana Guruji templates)."""
from __future__ import annotations

import datetime as dt
import uuid
from unittest.mock import patch

from app.services import sms_dlt


class TestDltTemplateBuilders:
    def test_otp_message_matches_jio_sample_layout(self):
        body = sms_dlt.build_dlt_otp_message("482910")
        assert body == (
            "Dear User,\n"
            "482910 is your OTP for Mana Guruji verification. "
            "Valid for 5 minutes. "
            "Please do not share this code with anyone.\n"
            "Thanks,\n"
            "Mana Guruji Team"
        )

    def test_booking_message_matches_jio_sample_layout(self):
        body = sms_dlt.build_dlt_booking_message(
            "Satyanarayana puja",
            "28 Nov 2026, 7:30 AM",
            "MG8K2P4Q",
        )
        assert body == (
            "Dear User,\n"
            "Your Satyanarayana puja booking is confirmed on 28 Nov 2026, 7:30 AM. "
            "Ref MG8K2P4Q. View details in the Mana Guruji app.\n"
            "Thanks,\n"
            "Mana Guruji Team"
        )

    def test_slot_label_format(self):
        label = sms_dlt.format_booking_slot_label(
            dt.date(2026, 11, 28),
            dt.time(7, 30),
        )
        assert label == "28 Nov 2026, 7:30 AM"


class TestDltSanitize:
    def test_otp_rejects_non_six_digit(self):
        assert sms_dlt.sanitize_dlt_number("12345") is None
        assert sms_dlt.sanitize_dlt_number("12ab56") is None
        assert sms_dlt.sanitize_dlt_number("123456") == "123456"

    def test_alphanumeric_strips_pipe(self):
        assert sms_dlt.sanitize_dlt_alphanumeric("A|B", field="x") == "A B"

    def test_booking_ref_from_uuid(self):
        bid = uuid.UUID("abcd0000-0000-0000-0000-000000000001")
        assert sms_dlt.booking_public_ref(bid) == "ABCD0000"


class TestDltReady:
    @patch("app.services.sms_dlt.get_settings")
    def test_otp_ready_with_message_id(self, mock_settings):
        s = mock_settings.return_value
        s.FAST2SMS_API_KEY = "k"
        s.FAST2SMS_SENDER_ID = "MNGURU"
        s.FAST2SMS_DLT_OTP_MESSAGE_ID = "40001"
        s.FAST2SMS_DLT_ENTITY_ID = ""
        assert sms_dlt.dlt_otp_ready() is True

    @patch("app.services.sms_dlt.get_settings")
    def test_otp_ready_manual_with_entity(self, mock_settings):
        s = mock_settings.return_value
        s.FAST2SMS_API_KEY = "k"
        s.FAST2SMS_SENDER_ID = "MNGURU"
        s.FAST2SMS_DLT_OTP_MESSAGE_ID = ""
        s.FAST2SMS_DLT_ENTITY_ID = "1701..."
        s.FAST2SMS_DLT_OTP_TEMPLATE_ID = ""
        assert sms_dlt.dlt_otp_ready() is True
        assert (
            sms_dlt.resolved_otp_template_id() == sms_dlt.DLT_OTP_CONTENT_TEMPLATE_ID
        )