"""
Notification worker (FCM push best-effort + MSG91 SMS fallback). Sync psycopg3.

Best-effort by design: GET /v1/offers polling is the delivery safety net, not
push. On FCM UNREGISTERED, delete the dead device row. Direct-offer push failure
escalates to SMS.
"""
from __future__ import annotations

import structlog

from app.workers.celery_app import celery_app

log = structlog.get_logger("notifications")


@celery_app.task(name="app.workers.notifications.notify_offers")
def notify_offers(booking_id: str) -> dict:
    # Look up live-offer pujaris, send FCM, fall back to SMS on failure.
    # Integration stubbed; logs so the pipeline is observable end to end.
    log.info("notify_offers", booking_id=booking_id)
    return {"notified": booking_id}


@celery_app.task(name="app.workers.notifications.notify_no_pujari")
def notify_no_pujari(booking_id: str) -> dict:
    log.info("notify_no_pujari", booking_id=booking_id)
    return {"notified": booking_id}


@celery_app.task(name="app.workers.notifications.alert_refund_failed")
def alert_refund_failed(refund_id: str) -> dict:
    log.error("alert_refund_failed", refund_id=refund_id)
    return {"alerted": refund_id}
