"""P-MONITOR — vendor-neutral ops alerting and Prometheus metrics."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import create_app
from app.monitoring.emit import AlertCandidate, record_ops_alert_sync
from app.monitoring.registry import AlertType
from app.monitoring.scanner import run_stuck_state_monitor
from app.workers.sweep import get_connection

CUSTOMER = "aaaaaaaa-0000-0000-0000-000000000001"
PUJARI_USER = "bbbbbbbb-0000-0000-0000-000000000001"
ADDRESS = "dddddddd-0000-0000-0000-000000000001"
PUJA = "11111111-1111-1111-1111-111111111111"


async def _pujari_id(session) -> str:
    return str(
        (
            await session.execute(
                text("SELECT id FROM pujaris WHERE user_id = :uid"),
                {"uid": PUJARI_USER},
            )
        ).scalar_one()
    )


def _unique_slot_time(uniq) -> str:
    h = (int(uniq.id().replace("-", "")[:4], 16) % 12) + 8
    m = int(uniq.id().replace("-", "")[4:8], 16) % 60
    return f"{h:02d}:{m:02d}:00"


@pytest.fixture(autouse=True)
async def _clear_pujari_stuck_bookings(session, seed):
    pid = await _pujari_id(session)
    await session.execute(
        text(
            """
            UPDATE bookings
            SET pujari_id = NULL, intended_pujari_id = NULL, updated_at = now()
            WHERE pujari_id = :pid AND cancelled_at IS NULL
            """
        ),
        {"pid": pid},
    )
    await session.execute(
        text(
            "DELETE FROM ops_monitor_alerts WHERE subject_id IN "
            "(SELECT id FROM bookings WHERE user_id = :uid)"
        ),
        {"uid": CUSTOMER},
    )
    await session.commit()


async def _insert_stuck_confirmed(session, uniq) -> str:
    pid = await _pujari_id(session)
    slot_time = _unique_slot_time(uniq)
    bid = uniq.id()
    await session.execute(
        text(
            """
            INSERT INTO bookings (
                id, user_id, pujari_id, intended_pujari_id, puja_id, address_id, status_id,
                cancellation_policy_id, scheduled_date, scheduled_time, duration_minutes,
                total_amount, amount_due_online, amount_due_offline, payment_mode, paid_at,
                dispatch_mode, booking_class, created_at, updated_at
            )
            SELECT
                :bid, :uid, :pid, :pid, :puja, :addr, st.id,
                (SELECT id FROM cancellation_policies WHERE name='standard'),
                CURRENT_DATE - INTERVAL '2 days', CAST(:t AS time), 90,
                2100, 2100, 0, 'full_online', now(),
                'broadcast', 'advance', now(), now()
            FROM status_types st
            WHERE st.domain = 'booking' AND st.code = 'confirmed'
            """
        ),
        {
            "bid": bid,
            "uid": CUSTOMER,
            "pid": pid,
            "puja": PUJA,
            "addr": ADDRESS,
            "t": slot_time,
        },
    )
    await session.commit()
    return bid


@pytest.mark.asyncio
async def test_stuck_confirmed_ops_monitor_alert(session, seed, uniq):
    bid = await _insert_stuck_confirmed(session, uniq)

    conn = get_connection()
    try:
        summary = run_stuck_state_monitor(conn)
    finally:
        conn.close()

    assert bid in summary["stuck_confirmed_no_show"]

    async with session.begin():
        row = (
            await session.execute(
                text(
                    """
                    SELECT alert_type, resolved_at IS NULL AS open
                    FROM ops_monitor_alerts
                    WHERE subject_id = :bid
                    """
                ),
                {"bid": bid},
            )
        ).mappings().first()
    assert row is not None
    assert row["alert_type"] == AlertType.STUCK_CONFIRMED_NO_SHOW.value
    assert row["open"] is True

    conn = get_connection()
    try:
        second = run_stuck_state_monitor(conn)
    finally:
        conn.close()
    assert bid not in second["stuck_confirmed_no_show"]


@pytest.mark.asyncio
async def test_ops_alert_idempotent_upsert(session, seed, uniq):
    bid = await _insert_stuck_confirmed(session, uniq)
    conn = get_connection()
    try:
        first = record_ops_alert_sync(
            conn,
            AlertCandidate(
                alert_type=AlertType.STUCK_CONFIRMED_NO_SHOW,
                subject_id=bid,
                payload={"booking_id": bid},
            ),
        )
        second = record_ops_alert_sync(
            conn,
            AlertCandidate(
                alert_type=AlertType.STUCK_CONFIRMED_NO_SHOW,
                subject_id=bid,
                payload={"booking_id": bid},
            ),
        )
    finally:
        conn.close()
    assert first is True
    assert second is False

    async with session.begin():
        count = (
            await session.execute(
                text(
                    "SELECT occurrence_count FROM ops_monitor_alerts "
                    "WHERE subject_id = :bid AND resolved_at IS NULL"
                ),
                {"bid": bid},
            )
        ).scalar_one()
    assert count == 2


def test_metrics_endpoint_exposes_prometheus():
    client = TestClient(create_app())
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "puja_ops_alert_events_total" in resp.text
    assert "puja_http_requests_total" in resp.text
