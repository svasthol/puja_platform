"""Stable ops-alert taxonomy — do not rename values (downstream alert rules depend on them)."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AlertType(StrEnum):
    STUCK_PAYMENT_PENDING = "stuck_payment_pending_webhook_loss"
    STUCK_CONFIRMED_NO_SHOW = "stuck_confirmed_no_show"
    REFUND_STALL = "refund_stall"
    REFUND_FAILED_PERMANENT = "refund_failed_permanent"
    DISPATCH_EXHAUSTED = "dispatch_exhausted"
    WEBHOOK_SIGNATURE_INVALID = "webhook_signature_invalid"


@dataclass(frozen=True, slots=True)
class AlertSpec:
    alert_type: AlertType
    severity: str  # info | warning | error | critical
    layer: str  # api | worker | sweep | data
    component: str  # booking | payment | refund | dispatch | webhook
    subject_type: str  # booking | refund | payment | webhook
    description: str


_ALERT_SPECS: dict[AlertType, AlertSpec] = {
    AlertType.STUCK_PAYMENT_PENDING: AlertSpec(
        alert_type=AlertType.STUCK_PAYMENT_PENDING,
        severity="warning",
        layer="sweep",
        component="payment",
        subject_type="booking",
        description="payment_pending past hold TTL + grace while payment succeeded (webhook loss)",
    ),
    AlertType.STUCK_CONFIRMED_NO_SHOW: AlertSpec(
        alert_type=AlertType.STUCK_CONFIRMED_NO_SHOW,
        severity="warning",
        layer="sweep",
        component="booking",
        subject_type="booking",
        description="confirmed past scheduled_time + grace without in_progress (no-show)",
    ),
    AlertType.REFUND_STALL: AlertSpec(
        alert_type=AlertType.REFUND_STALL,
        severity="warning",
        layer="data",
        component="refund",
        subject_type="refund",
        description="refund pending/processing with high attempt_count",
    ),
    AlertType.REFUND_FAILED_PERMANENT: AlertSpec(
        alert_type=AlertType.REFUND_FAILED_PERMANENT,
        severity="error",
        layer="worker",
        component="refund",
        subject_type="refund",
        description="refund exhausted retries — manual ops required",
    ),
    AlertType.DISPATCH_EXHAUSTED: AlertSpec(
        alert_type=AlertType.DISPATCH_EXHAUSTED,
        severity="warning",
        layer="worker",
        component="dispatch",
        subject_type="booking",
        description="dispatch deadline exhausted — failed_no_pujari",
    ),
    AlertType.WEBHOOK_SIGNATURE_INVALID: AlertSpec(
        alert_type=AlertType.WEBHOOK_SIGNATURE_INVALID,
        severity="error",
        layer="api",
        component="webhook",
        subject_type="webhook",
        description="Razorpay webhook HMAC verification failed",
    ),
}


def get_alert_spec(alert_type: AlertType) -> AlertSpec:
    return _ALERT_SPECS[alert_type]
