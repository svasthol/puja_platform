"""PR3 slice 3 — transactional SMS + reconcile recovery ops alerts."""

import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.sms_phone import InvalidIndiaPhoneError
from app.services.sms_router import send_transactional_sms_sync


def test_txn_sms_invalid_phone_returns_false():
    with patch(
        "app.services.fast2sms_client.send_transactional_sms_sync",
        side_effect=InvalidIndiaPhoneError(
            "Indian mobile numbers must start with 6, 7, 8, or 9."
        ),
    ):
        assert send_transactional_sms_sync("+910000009999", "test") is False


def test_notify_rm_escalation_completes_when_sms_skipped():
    from app.workers.notifications import _notify_rm_dispatch_escalation_impl

    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    cur.fetchall.return_value = []

    with (
        patch("app.workers.notifications.get_connection", return_value=conn),
        patch(
            "app.workers.notifications._resolve_rm_contact",
            return_value=(
                "+910000009999",
                "E2E RM",
                "Test Puja",
                "2026-11-16",
                "07:00:00",
                "00000000-0000-0000-0000-000000000001",
            ),
        ),
        patch(
            "app.services.fast2sms_client.send_transactional_sms_sync",
            side_effect=InvalidIndiaPhoneError(
                "Indian mobile numbers must start with 6, 7, 8, or 9."
            ),
        ),
    ):
        result = _notify_rm_dispatch_escalation_impl(
            "00000000-0000-0000-0000-000000000001", "approaching"
        )

    assert result["rm_sms"] is False
    assert result["level"] == "approaching"
    conn.commit.assert_called_once()


def test_rel010_reconcile_recovery_alert_registered():
    registry_py = Path(__file__).resolve().parents[1] / "app/monitoring/registry.py"
    text = registry_py.read_text(encoding="utf-8")
    assert "PAYMENT_RECONCILE_RECOVERED" in text
    assert '"payment_reconcile_recovered"' in text
    assert "reconcile worker applied a captured payment" in text


def test_reconcile_recovery_records_ops_alert():
    from app.workers.payment_reconcile import _record_reconcile_recovery

    conn = MagicMock()
    bid = uuid.UUID("00000000-0000-0000-0000-000000000099")
    mock_record = MagicMock()
    fake_emit = MagicMock(record_ops_alert_sync=mock_record)
    fake_emit.AlertCandidate = lambda **kwargs: SimpleNamespace(**kwargs)
    fake_registry = MagicMock()
    fake_registry.AlertType.PAYMENT_RECONCILE_RECOVERED = "payment_reconcile_recovered"

    with patch.dict(
        sys.modules,
        {
            "app.monitoring.emit": fake_emit,
            "app.monitoring.registry": fake_registry,
        },
    ):
        _record_reconcile_recovery(conn, booking_id=bid, pay_id="pay_test123")

    mock_record.assert_called_once()
    _conn, candidate = mock_record.call_args[0]
    assert _conn is conn
    assert candidate.subject_id == str(bid)
    assert candidate.payload == {"pay_id": "pay_test123", "source": "payment_reconcile"}