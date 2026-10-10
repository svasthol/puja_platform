"""
Notification worker (P-NOTIFY) — FCM push best-effort + MSG91 SMS fallback.

Sync psycopg3 + sync httpx (Celery workers). GET /v1/offers poll remains the
delivery safety net per DISPATCH_FLOW.md step 5.

Direct-offer push failure escalates to SMS (MSG91). FCM UNREGISTERED deletes the
dead devices row. Inserts in-app notification rows for audit.
"""
from __future__ import annotations

import uuid

import structlog

from app.services.fcm_client import FcmOutcome, send_push_sync
from app.services.sms_router import send_transactional_sms_sync
from app.workers.celery_app import celery_app
from app.workers.sweep import _agent_dbg, get_connection

log = structlog.get_logger("notifications")

_LIVE_OFFERS_SQL = """
SELECT ba.pujari_id, pj.user_id, u.phone, b.dispatch_mode, b.intended_pujari_id
FROM booking_assignments ba
JOIN status_types st ON st.id = ba.status_id AND st.domain = 'assignment' AND st.code = 'offered'
JOIN bookings b ON b.id = ba.booking_id
JOIN pujaris pj ON pj.id = ba.pujari_id
JOIN users u ON u.id = pj.user_id
WHERE ba.booking_id = %s
  AND ba.responded_at IS NULL
  AND ba.expires_at > now()
"""

_DEVICES_SQL = "SELECT device_token FROM devices WHERE user_id = %s"

_CUSTOMER_SQL = """
SELECT b.user_id, u.phone, puja.name AS puja_name
FROM bookings b
JOIN users u ON u.id = b.user_id
JOIN pujas puja ON puja.id = b.puja_id
WHERE b.id = %s
"""

_BOOKING_CLASS_SQL = "SELECT booking_class FROM bookings WHERE id = %s"


def _broadcast_offer_payload(
    booking_id: str, booking_class: str
) -> tuple[str, str, dict[str, str], str]:
    """FCM content for broadcast notify_offers (§21.6.H)."""
    if booking_class == "instant":
        return (
            "New puja offer",
            "You have an urgent booking offer — open the app to accept.",
            {"type": "offer_instant", "booking_id": booking_id},
            "high",
        )
    return (
        "New puja offer",
        "You have a new booking offer — open your inbox to view.",
        {"type": "offer_advance", "booking_id": booking_id},
        "normal",
    )


def _insert_notification(
    cur, *, user_id: str, app_context: str, related_type: str, related_id: str, title: str, body: str
) -> None:
    cur.execute(
        """
        INSERT INTO notifications (id, user_id, app_context, related_type, related_id, title, body, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, now())
        """,
        (str(uuid.uuid4()), user_id, app_context, related_type, related_id, title, body),
    )


def _push_to_user(
    cur,
    *,
    user_id: str,
    title: str,
    body: str,
    data: dict[str, str],
    priority: str = "high",
) -> tuple[int, int, int]:
    """Returns (sent, failed, unregistered_deleted)."""
    cur.execute(_DEVICES_SQL, (user_id,))
    tokens = [r[0] for r in cur.fetchall()]
    sent = failed = deleted = 0
    for tok in tokens:
        result = send_push_sync(
            tok, title=title, body=body, data=data, priority=priority
        )
        if result.outcome == FcmOutcome.SENT:
            sent += 1
        elif result.outcome == FcmOutcome.UNREGISTERED:
            cur.execute("DELETE FROM devices WHERE device_token = %s", (tok,))
            deleted += 1
            log.info("fcm_device_removed", token_tail=tok[-8:], reason=result.error)
        elif result.outcome == FcmOutcome.SKIPPED:
            failed += 1
        else:
            failed += 1
    return sent, failed, deleted


def _notify_offers_impl(booking_id: str) -> dict:
    _agent_dbg(
        "H5",
        "notifications.py:_notify_offers_impl",
        "notify_offers_enter",
        {"booking_id": booking_id},
    )
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(_BOOKING_CLASS_SQL, (booking_id,))
            class_row = cur.fetchone()
            booking_class = class_row[0] if class_row and class_row[0] else "advance"
            title, body, data, priority = _broadcast_offer_payload(booking_id, booking_class)

            cur.execute(_LIVE_OFFERS_SQL, (booking_id,))
            rows = cur.fetchall()
            if not rows:
                log.info("notify_offers_none_live", booking_id=booking_id)
                _agent_dbg(
                    "H6",
                    "notifications.py:_notify_offers_impl",
                    "notify_offers_no_live_assignments",
                    {"booking_id": booking_id},
                )
                return {"booking_id": booking_id, "targets": 0}

            total_sent = total_failed = total_deleted = 0
            sms_sent = 0
            is_direct = rows[0][3] == "direct" or rows[0][4] is not None

            for pujari_id, user_id, phone, _dm, _intended in rows:
                uid = str(user_id)
                sent, failed, deleted = _push_to_user(
                    cur,
                    user_id=uid,
                    title=title,
                    body=body,
                    data=data,
                    priority=priority,
                )
                total_sent += sent
                total_failed += failed
                total_deleted += deleted
                _insert_notification(
                    cur,
                    user_id=uid,
                    app_context="pujari",
                    related_type="assignment",
                    related_id=booking_id,
                    title=title,
                    body=body,
                )

                # Direct mode: escalate to SMS when every FCM attempt failed/skipped
                if is_direct and sent == 0 and phone:
                    msg = f"New direct puja offer for booking {booking_id[:8]}. Open partner app."
                    if send_transactional_sms_sync(phone, msg):
                        sms_sent += 1

            conn.commit()
            log.info(
                "notify_offers_done",
                booking_id=booking_id,
                booking_class=booking_class,
                offer_type=data["type"],
                targets=len(rows),
                fcm_sent=total_sent,
                fcm_failed=total_failed,
                devices_deleted=total_deleted,
                sms_fallback=sms_sent,
            )
            _agent_dbg(
                "H6",
                "notifications.py:_notify_offers_impl",
                "notify_offers_done",
                {
                    "booking_id": booking_id,
                    "targets": len(rows),
                    "fcm_sent": total_sent,
                    "fcm_failed": total_failed,
                    "devices_deleted": total_deleted,
                },
            )
            return {
                "booking_id": booking_id,
                "booking_class": booking_class,
                "offer_type": data["type"],
                "targets": len(rows),
                "fcm_sent": total_sent,
                "fcm_failed": total_failed,
                "devices_deleted": total_deleted,
                "sms_fallback": sms_sent,
            }
    finally:
        conn.close()


def _notify_no_pujari_impl(booking_id: str) -> dict:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(_CUSTOMER_SQL, (booking_id,))
            row = cur.fetchone()
            if row is None:
                return {"booking_id": booking_id, "skipped": "booking_missing"}
            user_id, phone, puja_name = str(row[0]), row[1], row[2]
            title = "No pujari available"
            body = f"We could not find a pujari for {puja_name}. A full refund will be processed."
            data = {"type": "no_pujari", "booking_id": booking_id}
            sent, failed, deleted = _push_to_user(
                cur, user_id=user_id, title=title, body=body, data=data
            )
            sms_ok = False
            if phone and (sent == 0 or failed > 0):
                sms_ok = send_transactional_sms_sync(
                    phone, f"No pujari available for your {puja_name} booking. Refund initiated."
                )
            _insert_notification(
                cur,
                user_id=user_id,
                app_context="customer",
                related_type="booking",
                related_id=booking_id,
                title=title,
                body=body,
            )
            conn.commit()
            log.info(
                "notify_no_pujari_done",
                booking_id=booking_id,
                fcm_sent=sent,
                sms=sms_ok,
                devices_deleted=deleted,
            )
            return {
                "booking_id": booking_id,
                "fcm_sent": sent,
                "sms": sms_ok,
                "devices_deleted": deleted,
            }
    finally:
        conn.close()


_PUJARI_RECONFIRM_SQL = """
SELECT pj.user_id, u.phone, pu.name AS puja_name, b.scheduled_date, b.scheduled_time
FROM bookings b
JOIN pujaris pj ON pj.id = b.pujari_id
JOIN users u ON u.id = pj.user_id
JOIN pujas pu ON pu.id = b.puja_id
WHERE b.id = %s
"""

_RM_ESCALATION_SQL = """
SELECT rm.phone, rm.name AS rm_name, pu.name AS puja_name,
       b.scheduled_date, b.scheduled_time, b.id
FROM bookings b
JOIN pujas pu ON pu.id = b.puja_id
LEFT JOIN relationship_managers rm ON rm.id = b.relationship_manager_id
WHERE b.id = %s
"""

_ADMIN_USERS_SQL = """
SELECT DISTINCT ur.user_id
FROM user_roles ur
JOIN roles r ON r.id = ur.role_id
WHERE r.name IN ('admin', 'support')
"""


def _notify_reconfirm_ping_impl(booking_id: str) -> dict:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(_PUJARI_RECONFIRM_SQL, (booking_id,))
            row = cur.fetchone()
            if row is None:
                return {"booking_id": booking_id, "skipped": "booking_missing"}
            user_id, phone, puja_name, sched_date, sched_time = row
            uid = str(user_id)
            title = "Confirm your attendance"
            body = (
                f"Please confirm you will perform {puja_name} on "
                f"{sched_date} at {sched_time}. Open the partner app."
            )
            data = {"type": "reconfirm_ping", "booking_id": booking_id}
            sent, failed, deleted = _push_to_user(
                cur, user_id=uid, title=title, body=body, data=data
            )
            sms_ok = False
            if phone and sent == 0:
                sms_ok = send_transactional_sms_sync(
                    phone,
                    f"Mana Guruji: confirm attendance for {puja_name} on {sched_date}. "
                    "Open partner app.",
                )
            _insert_notification(
                cur,
                user_id=uid,
                app_context="pujari",
                related_type="booking",
                related_id=booking_id,
                title=title,
                body=body,
            )
            conn.commit()
            log.info(
                "reconfirm_ping_sent",
                booking_id=booking_id,
                fcm_sent=sent,
                sms=sms_ok,
            )
            return {
                "booking_id": booking_id,
                "fcm_sent": sent,
                "sms": sms_ok,
                "devices_deleted": deleted,
            }
    finally:
        conn.close()


def _resolve_rm_contact(cur, booking_id: str) -> tuple[str | None, str | None, str, str, str]:
    """Return RM phone/name + puja/slot context for dispatch escalation alerts."""
    cur.execute(_RM_ESCALATION_SQL, (booking_id,))
    row = cur.fetchone()
    if row is None:
        return None, None, "", "", booking_id
    rm_phone, _rm_name, puja_name, sched_date, sched_time, bid = row
    if rm_phone:
        return rm_phone, _rm_name, puja_name, str(sched_date), str(sched_time), str(bid)

    cur.execute(
        """
        SELECT rm.phone, rm.name
        FROM platform_settings ps
        JOIN relationship_managers rm
          ON rm.id = (ps.value_json->>'relationship_manager_id')::uuid
        WHERE ps.key = 'default_relationship_manager_id'
          AND rm.is_active
        """
    )
    default = cur.fetchone()
    if default and default[0]:
        return default[0], default[1], puja_name, str(sched_date), str(sched_time), str(bid)

    cur.execute(
        """
        SELECT rm.phone, rm.name
        FROM bookings b
        JOIN addresses a ON a.id = b.address_id
        JOIN relationship_managers rm ON rm.city = a.city AND rm.is_active
        WHERE b.id = %s
        ORDER BY rm.updated_at DESC
        LIMIT 1
        """,
        (booking_id,),
    )
    city_rm = cur.fetchone()
    if city_rm and city_rm[0]:
        return city_rm[0], city_rm[1], puja_name, str(sched_date), str(sched_time), str(bid)

    cur.execute(
        """
        SELECT phone, name FROM relationship_managers
        WHERE is_active
        ORDER BY updated_at DESC
        LIMIT 1
        """
    )
    fallback = cur.fetchone()
    if fallback:
        return fallback[0], fallback[1], puja_name, str(sched_date), str(sched_time), str(bid)
    return None, None, puja_name, str(sched_date), str(sched_time), str(bid)


def _notify_rm_dispatch_escalation_impl(booking_id: str, level: str) -> dict:
    """RM + admin alert for unaccepted advance booking (§21.6.F)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            rm_phone, _rm_name, puja_name, sched_date, sched_time, bid = _resolve_rm_contact(
                cur, booking_id
            )
            if level == "approaching":
                title = "Urgent: no pujari accepted"
                body = (
                    f"Advance booking {bid[:8]} for {puja_name} on {sched_date} at "
                    f"{sched_time} is within 24h with no pujari. Follow up immediately."
                )
                sms_prefix = "Mana Guruji URGENT RM alert"
            else:
                title = "No pujari accepted yet"
                body = (
                    f"Advance booking {bid[:8]} for {puja_name} on {sched_date} at "
                    f"{sched_time} has had no acceptance for 24h+. Please follow up."
                )
                sms_prefix = "Mana Guruji RM alert"

            sms_ok = False
            if rm_phone:
                sms_ok = send_transactional_sms_sync(
                    rm_phone,
                    f"{sms_prefix}: no pujari accepted for {puja_name} on {sched_date}. "
                    "Please follow up.",
                )
            cur.execute(_ADMIN_USERS_SQL)
            admin_count = 0
            for (admin_user_id,) in cur.fetchall():
                _insert_notification(
                    cur,
                    user_id=str(admin_user_id),
                    app_context="admin",
                    related_type="booking",
                    related_id=booking_id,
                    title=title,
                    body=body,
                )
                admin_count += 1
            conn.commit()
            log.info(
                "rm_dispatch_escalation_sent",
                booking_id=booking_id,
                level=level,
                rm_phone=bool(rm_phone),
                rm_sms=sms_ok,
                admin_notifications=admin_count,
            )
            return {
                "booking_id": booking_id,
                "level": level,
                "rm_sms": sms_ok,
                "admin_notifications": admin_count,
            }
    finally:
        conn.close()


def _notify_reconfirm_escalation_impl(booking_id: str) -> dict:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(_RM_ESCALATION_SQL, (booking_id,))
            row = cur.fetchone()
            if row is None:
                return {"booking_id": booking_id, "skipped": "booking_missing"}
            rm_phone, rm_name, puja_name, sched_date, sched_time, bid = row
            title = "Pujari attendance not confirmed"
            body = (
                f"No attendance confirmation for {puja_name} on {sched_date} "
                f"at {sched_time} (booking {str(bid)[:8]}). Contact pujari and customer."
            )
            sms_ok = False
            if rm_phone:
                sms_ok = send_transactional_sms_sync(
                    rm_phone,
                    f"Mana Guruji RM alert: pujari has not confirmed {puja_name} "
                    f"on {sched_date}. Please follow up.",
                )
            cur.execute(_ADMIN_USERS_SQL)
            admin_count = 0
            for (admin_user_id,) in cur.fetchall():
                _insert_notification(
                    cur,
                    user_id=str(admin_user_id),
                    app_context="admin",
                    related_type="booking",
                    related_id=booking_id,
                    title=title,
                    body=body,
                )
                admin_count += 1
            conn.commit()
            log.info(
                "reconfirm_escalation_sent",
                booking_id=booking_id,
                rm_phone=bool(rm_phone),
                rm_sms=sms_ok,
                admin_notifications=admin_count,
            )
            return {
                "booking_id": booking_id,
                "rm_sms": sms_ok,
                "admin_notifications": admin_count,
            }
    finally:
        conn.close()


def _notify_accept_ack_impl(booking_id: str, pujari_user_id: str) -> dict:
    """Advance-class accept acknowledgement push (§21.6.H)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(_BOOKING_CLASS_SQL, (booking_id,))
            row = cur.fetchone()
            if row is None or row[0] != "advance":
                return {"booking_id": booking_id, "skipped": "not_advance"}

            title = "Added to your Bookings"
            body = "Added to your Bookings — we'll confirm ~24h before."
            data = {"type": "accept_ack", "booking_id": booking_id}
            sent, failed, deleted = _push_to_user(
                cur,
                user_id=pujari_user_id,
                title=title,
                body=body,
                data=data,
                priority="normal",
            )
            _insert_notification(
                cur,
                user_id=pujari_user_id,
                app_context="pujari",
                related_type="booking",
                related_id=booking_id,
                title=title,
                body=body,
            )
            conn.commit()
            log.info(
                "accept_ack_sent",
                booking_id=booking_id,
                pujari_user_id=pujari_user_id,
                fcm_sent=sent,
            )
            return {
                "booking_id": booking_id,
                "fcm_sent": sent,
                "fcm_failed": failed,
                "devices_deleted": deleted,
            }
    finally:
        conn.close()


_WITHDRAWN_TARGETS_SQL = """
SELECT DISTINCT pj.user_id
FROM booking_assignments ba
JOIN pujaris pj ON pj.id = ba.pujari_id
JOIN bookings b ON b.id = ba.booking_id
JOIN status_types st ON st.id = ba.status_id
    AND st.domain = 'assignment' AND st.code = 'expired'
WHERE ba.booking_id = %s
  AND b.cancelled_at IS NOT NULL
"""


def _notify_offer_withdrawn_impl(booking_id: str) -> dict:
    """Partner push when customer cancels — `offer_withdrawn` (P-FCM-CUSTOMER-CANCEL)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(_WITHDRAWN_TARGETS_SQL, (booking_id,))
            user_ids = [str(row[0]) for row in cur.fetchall()]
            if not user_ids:
                log.info("notify_offer_withdrawn_none", booking_id=booking_id)
                return {"booking_id": booking_id, "targets": 0}

            title = "Offer withdrawn"
            body = "The customer cancelled this booking."
            data = {"type": "offer_withdrawn", "booking_id": booking_id}
            total_sent = total_failed = total_deleted = 0

            for uid in user_ids:
                sent, failed, deleted = _push_to_user(
                    cur,
                    user_id=uid,
                    title=title,
                    body=body,
                    data=data,
                    priority="normal",
                )
                total_sent += sent
                total_failed += failed
                total_deleted += deleted
                _insert_notification(
                    cur,
                    user_id=uid,
                    app_context="pujari",
                    related_type="assignment",
                    related_id=booking_id,
                    title=title,
                    body=body,
                )

            conn.commit()
            log.info(
                "notify_offer_withdrawn_done",
                booking_id=booking_id,
                targets=len(user_ids),
                fcm_sent=total_sent,
                fcm_failed=total_failed,
                devices_deleted=total_deleted,
            )
            return {
                "booking_id": booking_id,
                "targets": len(user_ids),
                "fcm_sent": total_sent,
                "fcm_failed": total_failed,
                "devices_deleted": total_deleted,
            }
    finally:
        conn.close()


def _notify_offer_instant_impl(booking_id: str) -> dict:
    """High-priority modal push on urgency flip (§21.6.E)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(_LIVE_OFFERS_SQL, (booking_id,))
            rows = cur.fetchall()
            if not rows:
                log.info("notify_offer_instant_none_live", booking_id=booking_id)
                return {"booking_id": booking_id, "targets": 0}

            total_sent = total_failed = total_deleted = 0
            for pujari_id, user_id, _phone, _dm, _intended in rows:
                uid = str(user_id)
                title = "Urgent puja offer"
                body = "A booking needs immediate attention — open the app to accept."
                data = {"type": "offer_instant", "booking_id": booking_id}
                sent, failed, deleted = _push_to_user(
                    cur, user_id=uid, title=title, body=body, data=data
                )
                total_sent += sent
                total_failed += failed
                total_deleted += deleted
                _insert_notification(
                    cur,
                    user_id=uid,
                    app_context="pujari",
                    related_type="assignment",
                    related_id=booking_id,
                    title=title,
                    body=body,
                )

            conn.commit()
            log.info(
                "notify_offer_instant_done",
                booking_id=booking_id,
                targets=len(rows),
                fcm_sent=total_sent,
            )
            return {
                "booking_id": booking_id,
                "targets": len(rows),
                "fcm_sent": total_sent,
                "fcm_failed": total_failed,
                "devices_deleted": total_deleted,
            }
    finally:
        conn.close()


@celery_app.task(name="app.workers.notifications.notify_accept_ack")
def notify_accept_ack(booking_id: str, pujari_user_id: str) -> dict:
    return _notify_accept_ack_impl(booking_id, pujari_user_id)


@celery_app.task(name="app.workers.notifications.notify_offers")
def notify_offers(booking_id: str) -> dict:
    return _notify_offers_impl(booking_id)


@celery_app.task(name="app.workers.notifications.notify_offer_instant")
def notify_offer_instant(booking_id: str) -> dict:
    return _notify_offer_instant_impl(booking_id)


@celery_app.task(name="app.workers.notifications.notify_rm_dispatch_escalation")
def notify_rm_dispatch_escalation(booking_id: str, level: str) -> dict:
    return _notify_rm_dispatch_escalation_impl(booking_id, level)


@celery_app.task(name="app.workers.notifications.notify_no_pujari")
def notify_no_pujari(booking_id: str) -> dict:
    return _notify_no_pujari_impl(booking_id)


@celery_app.task(name="app.workers.notifications.alert_refund_failed")
def alert_refund_failed(refund_id: str) -> dict:
    log.error("alert_refund_failed", refund_id=refund_id)
    return {"alerted": refund_id}


@celery_app.task(name="app.workers.notifications.notify_reconfirm_ping")
def notify_reconfirm_ping(booking_id: str) -> dict:
    return _notify_reconfirm_ping_impl(booking_id)


@celery_app.task(name="app.workers.notifications.notify_reconfirm_escalation")
def notify_reconfirm_escalation(booking_id: str) -> dict:
    return _notify_reconfirm_escalation_impl(booking_id)


@celery_app.task(name="app.workers.notifications.notify_offer_withdrawn")
def notify_offer_withdrawn(booking_id: str) -> dict:
    return _notify_offer_withdrawn_impl(booking_id)
