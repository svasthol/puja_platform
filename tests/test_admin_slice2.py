"""Sprint 4C slice 2 — A-REASSIGN, A-REFUND (LG-manual-reassign)."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.api.v1.endpoints import admin_bookings as bookings_ep
from app.api.v1.endpoints import admin_refunds as refunds_ep
from app.core.dependencies import Principal
from app.schemas.admin_bookings import AdminReassignRequest
from app.schemas.admin_refunds import RefundOverrideRequest

CUSTOMER = "aaaaaaaa-0000-0000-0000-000000000001"
PUJARI_USER = "bbbbbbbb-0000-0000-0000-000000000001"
PUJARI_USER2 = "bbbbbbbb-0000-0000-0000-000000000002"
ADDRESS = "dddddddd-0000-0000-0000-000000000001"
PUJA = "11111111-1111-1111-1111-111111111111"


class _FakeRequest:
    client = None


def _admin(uid: uuid.UUID) -> Principal:
    return Principal(user_id=uid, app_context="admin", roles=("admin",))


def _support(uid: uuid.UUID) -> Principal:
    return Principal(user_id=uid, app_context="admin", roles=("support",))


async def _mk_admin(session) -> uuid.UUID:
    uid = uuid.uuid4()
    await session.execute(
        text("INSERT INTO users (id, full_name, phone) VALUES (:id, 'Admin', :ph)"),
        {"id": str(uid), "ph": "+91975" + uuid.uuid4().hex[:7]},
    )
    return uid


async def _mk_support(session) -> uuid.UUID:
    uid = await _mk_admin(session)
    await session.execute(
        text("INSERT INTO roles (name) VALUES ('support') ON CONFLICT (name) DO NOTHING")
    )
    rid = (
        await session.execute(text("SELECT id FROM roles WHERE name='support'"))
    ).scalar_one()
    await session.execute(
        text(
            "INSERT INTO user_roles (user_id, role_id, assigned_at) VALUES (:uid, :rid, now())"
        ),
        {"uid": str(uid), "rid": rid},
    )
    return uid


def _unique_slot_time(uniq) -> str:
    h = (int(uniq.id().replace("-", "")[:4], 16) % 12) + 8
    m = int(uniq.id().replace("-", "")[4:8], 16) % 60
    return f"{h:02d}:{m:02d}:00"


async def _pujari_ids(session) -> tuple[str, str]:
    """Resolve pujari row ids from canonical seed users (E2E may use different UUIDs)."""
    p1 = (
        await session.execute(
            text("SELECT id FROM pujaris WHERE user_id = :uid"),
            {"uid": PUJARI_USER},
        )
    ).scalar_one()
    p2 = (
        await session.execute(
            text("SELECT id FROM pujaris WHERE user_id = :uid"),
            {"uid": PUJARI_USER2},
        )
    ).scalar_one()
    return str(p1), str(p2)


@pytest.fixture(autouse=True)
async def _clear_near_term_pujari_bookings(session, seed):
    """Avoid ex_bookings_pujari_no_overlap collisions across reruns."""
    p1, p2 = await _pujari_ids(session)
    await session.execute(
        text(
            """
            UPDATE bookings SET cancelled_at = now(), updated_at = now()
            WHERE pujari_id = ANY(:pids)
              AND cancelled_at IS NULL
              AND scheduled_date <= CURRENT_DATE + INTERVAL '14 days'
            """
        ),
        {"pids": [p1, p2]},
    )
    await session.commit()


async def _insert_confirmed_with_accepted_assignment(
    session,
    uniq,
    *,
    pujari_id: str | None = None,
) -> tuple[str, str]:
    if pujari_id is None:
        pujari_id, _ = await _pujari_ids(session)
    bid = uniq.id()
    aid = uuid.uuid4()
    slot_time = _unique_slot_time(uniq)
    await session.execute(
        text(
            """
            INSERT INTO bookings (
                id, user_id, pujari_id, intended_pujari_id, puja_id, address_id, status_id,
                cancellation_policy_id, scheduled_date, scheduled_time, duration_minutes,
                total_amount, amount_due_online, amount_due_offline, payment_mode, paid_at,
                dispatch_mode, created_at, updated_at
            )
            SELECT
                :bid, :uid, :pid, :pid, :puja, :addr, st.id,
                (SELECT id FROM cancellation_policies WHERE name='standard'),
                :d, CAST(:t AS time), 90, 2100, 2100, 0, 'full_online', now(),
                'broadcast', now(), now()
            FROM status_types st
            WHERE st.domain = 'booking' AND st.code = 'confirmed'
            """
        ),
        {
            "bid": bid,
            "uid": CUSTOMER,
            "pid": pujari_id,
            "puja": PUJA,
            "addr": ADDRESS,
            "d": uniq.date,
            "t": slot_time,
        },
    )
    await session.execute(
        text(
            """
            INSERT INTO booking_assignments (
                id, booking_id, pujari_id, status_id, offered_at, expires_at, responded_at
            ) VALUES (
                :aid, :bid, :pid,
                (SELECT id FROM status_types WHERE domain='assignment' AND code='accepted'),
                now(), now() + interval '5 minutes', now()
            )
            """
        ),
        {"aid": str(aid), "bid": bid, "pid": pujari_id},
    )
    await session.commit()
    return bid, str(aid)


async def _insert_success_payment(session, booking_id: str, uniq) -> str:
    pay_id = uniq.id()
    await session.execute(
        text(
            """
            INSERT INTO payments (
                id, booking_id, amount, idempotency_key, gateway_txn_id, status, created_at
            ) VALUES (:pid, :bid, 2100, :key, :gw, 'success', now())
            """
        ),
        {"pid": pay_id, "bid": booking_id, "key": f"idem-{uniq.id()}", "gw": f"pay_{uniq.id()}"},
    )
    await session.commit()
    return pay_id


@pytest.mark.asyncio
async def test_lg_manual_reassign(session, seed, uniq):
    """LG-manual-reassign: one accepted assignment; old row revoked."""
    pujari1, pujari2 = await _pujari_ids(session)
    bid, old_aid = await _insert_confirmed_with_accepted_assignment(session, uniq, pujari_id=pujari1)
    actor = await _mk_admin(session)
    await session.commit()

    resp = await bookings_ep.reassign_booking(
        uuid.UUID(bid),
        AdminReassignRequest(new_pujari_id=uuid.UUID(pujari2), change_reason="ops test"),
        _FakeRequest(),
        _admin(actor),
        session,
    )
    await session.commit()

    assert resp.old_pujari_id == uuid.UUID(pujari1)
    assert resp.new_pujari_id == uuid.UUID(pujari2)
    assert resp.status == "confirmed"

    booking = (
        await session.execute(
            text(
                """
                SELECT pujari_id, intended_pujari_id
                FROM bookings WHERE id = :bid
                """
            ),
            {"bid": bid},
        )
    ).mappings().first()
    assert str(booking["pujari_id"]) == pujari2
    assert str(booking["intended_pujari_id"]) == pujari2

    assignments = (
        await session.execute(
            text(
                """
                SELECT ast.code AS status, ba.id
                FROM booking_assignments ba
                JOIN status_types ast ON ast.id = ba.status_id
                WHERE ba.booking_id = :bid
                ORDER BY ba.offered_at ASC
                """
            ),
            {"bid": bid},
        )
    ).mappings().all()
    accepted = [a for a in assignments if a["status"] == "accepted"]
    revoked = [a for a in assignments if a["status"] == "revoked"]
    assert len(accepted) == 1
    assert str(accepted[0]["id"]) == str(resp.assignment_id)
    assert len(revoked) == 1
    assert str(revoked[0]["id"]) == old_aid

    audit = (
        await session.execute(
            text(
                "SELECT action FROM admin_audit_log WHERE actor_user_id = :uid AND entity_id = :bid"
            ),
            {"uid": str(actor), "bid": bid},
        )
    ).scalar_one()
    assert audit == "reassign"


@pytest.mark.asyncio
async def test_reassign_blocked_in_progress(session, seed, uniq):
    _, pujari2 = await _pujari_ids(session)
    bid, _ = await _insert_confirmed_with_accepted_assignment(session, uniq)
    in_progress_id = (
        await session.execute(
            text("SELECT id FROM status_types WHERE domain='booking' AND code='in_progress'")
        )
    ).scalar_one()
    await session.execute(
        text("UPDATE bookings SET status_id = :sid WHERE id = :bid"),
        {"sid": in_progress_id, "bid": bid},
    )
    actor = await _mk_admin(session)
    await session.commit()

    with pytest.raises(HTTPException) as exc:
        await bookings_ep.reassign_booking(
            uuid.UUID(bid),
            AdminReassignRequest(new_pujari_id=uuid.UUID(pujari2)),
            _FakeRequest(),
            _admin(actor),
            session,
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_support_can_reassign(session, seed, uniq):
    _, pujari2 = await _pujari_ids(session)
    bid, _ = await _insert_confirmed_with_accepted_assignment(session, uniq)
    actor = await _mk_support(session)
    await session.commit()

    resp = await bookings_ep.reassign_booking(
        uuid.UUID(bid),
        AdminReassignRequest(new_pujari_id=uuid.UUID(pujari2)),
        _FakeRequest(),
        _support(actor),
        session,
    )
    assert resp.new_pujari_id == uuid.UUID(pujari2)


@pytest.mark.asyncio
async def test_refund_override_admin(session, seed, uniq):
    bid, _ = await _insert_confirmed_with_accepted_assignment(session, uniq)
    pay_id = await _insert_success_payment(session, bid, uniq)
    actor = await _mk_admin(session)
    await session.commit()

    resp = await refunds_ep.refund_override(
        RefundOverrideRequest(booking_id=uuid.UUID(bid), amount=Decimal("500")),
        _FakeRequest(),
        _admin(actor),
        session,
    )
    await session.commit()

    assert resp.payment_id == uuid.UUID(pay_id)
    assert resp.amount == Decimal("500")
    assert resp.status == "pending"

    row = (
        await session.execute(
            text("SELECT reason, status FROM refunds WHERE id = :rid"),
            {"rid": str(resp.refund_id)},
        )
    ).mappings().first()
    assert row["reason"] == "admin_override"
    assert row["status"] == "pending"


@pytest.mark.asyncio
async def test_refund_support_within_cap(session, seed, uniq):
    bid, _ = await _insert_confirmed_with_accepted_assignment(session, uniq)
    await _insert_success_payment(session, bid, uniq)
    actor = await _mk_support(session)
    await session.commit()

    resp = await refunds_ep.refund_override(
        RefundOverrideRequest(booking_id=uuid.UUID(bid), amount=Decimal("1000")),
        _FakeRequest(),
        _support(actor),
        session,
    )
    assert resp.amount == Decimal("1000")


@pytest.mark.asyncio
async def test_refund_support_exceeds_per_action_cap(session, seed, uniq):
    bid, _ = await _insert_confirmed_with_accepted_assignment(session, uniq)
    await _insert_success_payment(session, bid, uniq)
    actor = await _mk_support(session)
    await session.commit()

    with pytest.raises(HTTPException) as exc:
        await refunds_ep.refund_override(
            RefundOverrideRequest(booking_id=uuid.UUID(bid), amount=Decimal("10000")),
            _FakeRequest(),
            _support(actor),
            session,
        )
    assert exc.value.status_code == 403
    assert "per-action cap" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_refund_support_exceeds_daily_cap(session, seed, uniq):
    """Support daily cap sums prior refund_override audit rows (IST day boundary)."""
    bid, _ = await _insert_confirmed_with_accepted_assignment(session, uniq)
    await _insert_success_payment(session, bid, uniq)
    actor = await _mk_support(session)
    await session.execute(
        text(
            """
            INSERT INTO platform_settings (key, value_json, updated_at)
            VALUES
                ('support_refund_cap_daily', '{"amount": 500}', now()),
                ('support_refund_cap_per_action', '{"amount": 5000}', now())
            ON CONFLICT (key) DO UPDATE
            SET value_json = EXCLUDED.value_json, updated_at = now()
            """
        )
    )
    await session.execute(
        text(
            """
            INSERT INTO admin_audit_log (
                id, actor_user_id, action, entity_type, entity_id, after_json, created_at
            ) VALUES (
                :id, :uid, 'refund_override', 'refund', :eid,
                '{"amount": "400"}'::jsonb, now()
            )
            """
        ),
        {"id": str(uuid.uuid4()), "uid": str(actor), "eid": str(uuid.uuid4())},
    )
    await session.commit()

    with pytest.raises(HTTPException) as exc:
        await refunds_ep.refund_override(
            RefundOverrideRequest(booking_id=uuid.UUID(bid), amount=Decimal("200")),
            _FakeRequest(),
            _support(actor),
            session,
        )
    assert exc.value.status_code == 403
    assert "daily cap" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_list_failed_permanent_refunds(session, seed, uniq):
    bid, _ = await _insert_confirmed_with_accepted_assignment(session, uniq)
    pay_id = await _insert_success_payment(session, bid, uniq)
    rid = uniq.id()
    await session.execute(
        text(
            """
            INSERT INTO refunds (
                id, payment_id, booking_id, amount, reason, status,
                attempt_count, next_attempt_at, last_error, created_at
            ) VALUES (
                :rid, :pid, :bid, 500, 'admin_override', 'failed_permanent',
                5, now(), 'gateway error', now()
            )
            """
        ),
        {"rid": rid, "pid": pay_id, "bid": bid},
    )
    actor = await _mk_admin(session)
    await session.commit()

    page = await refunds_ep.list_refunds(
        refund_status="failed_permanent",
        cursor=None,
        limit=20,
        _p=_admin(actor),
        db=session,
    )
    ids = {str(r.id) for r in page.refunds}
    assert rid in ids
    item = next(r for r in page.refunds if str(r.id) == rid)
    assert item.last_error == "gateway error"
    assert item.customer_phone is not None
