"""Sprint 4C slice 1 — P-EXC-ADMIN-PATHS, A-SEARCH, A-BOOKING-DETAIL."""
from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException
from psycopg.errors import ExclusionViolation, UniqueViolation
from sqlalchemy import text

from app.api.v1.endpoints import admin_bookings as bookings_ep
from app.core.dependencies import Principal
from app.core.exceptions import map_db_error

CUSTOMER = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
PUJARI_USER = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000001")
ADDRESS = uuid.UUID("dddddddd-0000-0000-0000-000000000001")
PUJA = uuid.UUID("11111111-1111-1111-1111-111111111111")


async def _ensure_customer(session, uniq) -> tuple[uuid.UUID, str, uuid.UUID]:
    """Self-contained customer + address for admin booking tests."""
    uid = uuid.uuid4()
    phone = f"+9198{uniq.id().replace('-', '')[:8]}"
    await session.execute(
        text("INSERT INTO users (id, full_name, phone) VALUES (:id, 'AdminBk', :ph)"),
        {"id": str(uid), "ph": phone},
    )
    area_id = (
        await session.execute(
            text(
                "SELECT id FROM service_areas WHERE city='Hyderabad' AND zone_name='Test Zone' "
                "UNION ALL SELECT id FROM service_areas LIMIT 1"
            )
        )
    ).scalar_one()
    aid = uuid.uuid4()
    await session.execute(
        text(
            """
            INSERT INTO addresses (
                id, user_id, line1, city, latitude, longitude, service_area_id, geom
            ) VALUES (
                :aid, :uid, 'Admin test', 'Hyderabad', 17.4, 78.4, :area,
                ST_SetSRID(ST_MakePoint(78.4, 17.4), 4326)::geography
            )
            """
        ),
        {"aid": str(aid), "uid": str(uid), "area": area_id},
    )
    return uid, phone, aid


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
        {"id": str(uid), "ph": "+91974" + uuid.uuid4().hex[:7]},
    )
    return uid


async def _seed_pujari_id(session) -> str:
    pid = (
        await session.execute(
            text("SELECT id FROM pujaris WHERE user_id = :uid"),
            {"uid": str(PUJARI_USER)},
        )
    ).scalar_one()
    return str(pid)


async def _insert_booking(session, uniq) -> tuple[str, str]:
    uid, phone, addr_id = await _ensure_customer(session, uniq)
    bid = uniq.id()
    await session.execute(
        text(
            """
            INSERT INTO bookings (
                id, user_id, puja_id, address_id, status_id, cancellation_policy_id,
                scheduled_date, scheduled_time, duration_minutes, total_amount,
                amount_due_online, amount_due_offline, payment_mode, paid_at,
                dispatch_mode, created_at, updated_at
            ) VALUES (
                :bid, :uid, :puja, :addr,
                (SELECT id FROM status_types WHERE domain='booking' AND code='requested'),
                (SELECT id FROM cancellation_policies WHERE name='standard'),
                CAST(:d AS date), CAST(:t AS time), 90, 2100, 2100, 0, 'full_online', now(),
                'broadcast', now(), now()
            )
            """
        ),
        {
            "bid": bid,
            "uid": str(uid),
            "puja": str(PUJA),
            "addr": str(addr_id),
            "d": uniq.date,
            "t": "10:30:00",
        },
    )
    await session.commit()
    return bid, phone


def test_refund_active_maps_409_on_admin_path():
    exc = UniqueViolation(
        'duplicate key value violates unique constraint "ux_refunds_one_active_per_payment"'
    )
    resp = map_db_error(exc, "/v1/admin/refunds/override")
    webhook_resp = map_db_error(exc, "/v1/webhooks/razorpay")
    assert resp.status_code == 409
    assert b"already in progress" in resp.body
    assert webhook_resp.status_code == 200


def test_pujari_overlap_maps_admin_copy_on_admin_path():
    exc = ExclusionViolation(
        'conflicting key value violates exclusion constraint "ex_bookings_pujari_no_overlap"'
    )
    admin_resp = map_db_error(exc, "/v1/admin/bookings/x/reassign")
    partner_resp = map_db_error(exc, "/v1/offers/x/accept")
    assert admin_resp.status_code == 409
    assert b"Target pujari" in admin_resp.body
    assert partner_resp.status_code == 409
    assert b"another booking of yours" in partner_resp.body


@pytest.mark.asyncio
async def test_search_by_phone_returns_booking_and_audits(session, seed, uniq):
    bid, phone = await _insert_booking(session, uniq)
    actor = await _mk_admin(session)
    await session.commit()

    page = await bookings_ep.search_bookings(
        _FakeRequest(),
        phone=phone[-10:],
        booking_id=None,
        booking_status=None,
        date_from=None,
        date_to=None,
        cursor=None,
        limit=20,
        p=_admin(actor),
        db=session,
    )
    await session.commit()
    ids = {str(b.id) for b in page.bookings}
    assert bid in ids

    audit = (
        await session.execute(
            text(
                "SELECT action, entity_type, after_json FROM admin_audit_log "
                "WHERE actor_user_id = :uid ORDER BY created_at DESC LIMIT 1"
            ),
            {"uid": str(actor)},
        )
    ).mappings().first()
    assert audit is not None
    assert audit["action"] == "read"
    assert audit["entity_type"] == "booking"
    assert audit["after_json"]["phone"] == phone[-10:]


@pytest.mark.asyncio
async def test_search_by_booking_id(session, seed, uniq):
    bid, _phone = await _insert_booking(session, uniq)
    actor = await _mk_admin(session)
    await session.commit()

    page = await bookings_ep.search_bookings(
        _FakeRequest(),
        phone=None,
        booking_id=uuid.UUID(bid),
        booking_status=None,
        date_from=None,
        date_to=None,
        cursor=None,
        limit=20,
        p=_admin(actor),
        db=session,
    )
    assert len(page.bookings) == 1
    assert str(page.bookings[0].id) == bid


@pytest.mark.asyncio
async def test_search_invalid_status_422(session, seed):
    actor = await _mk_admin(session)
    await session.commit()
    with pytest.raises(HTTPException) as exc:
        await bookings_ep.search_bookings(
            _FakeRequest(),
            phone=None,
            booking_id=None,
            booking_status="not_a_status",
            date_from=None,
            date_to=None,
            cursor=None,
            limit=20,
            p=_admin(actor),
            db=session,
        )
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_support_role_can_search(session, seed, uniq):
    bid, phone = await _insert_booking(session, uniq)
    actor = await _mk_admin(session)
    await session.execute(
        text(
            "INSERT INTO roles (name) VALUES ('support') ON CONFLICT (name) DO NOTHING"
        )
    )
    rid = (
        await session.execute(text("SELECT id FROM roles WHERE name='support'"))
    ).scalar_one()
    await session.execute(
        text(
            "INSERT INTO user_roles (user_id, role_id, assigned_at) VALUES (:uid, :rid, now())"
        ),
        {"uid": str(actor), "rid": rid},
    )
    await session.commit()

    page = await bookings_ep.search_bookings(
        _FakeRequest(),
        phone=phone[-10:],
        booking_id=None,
        booking_status=None,
        date_from=None,
        date_to=None,
        cursor=None,
        limit=20,
        p=_support(actor),
        db=session,
    )
    assert bid in {str(b.id) for b in page.bookings}


@pytest.mark.asyncio
async def test_booking_detail_360(session, seed, uniq):
    bid, phone = await _insert_booking(session, uniq)
    pid = await _seed_pujari_id(session)
    aid = uniq.id()
    await session.execute(
        text(
            """
            INSERT INTO booking_assignments (
                id, booking_id, pujari_id, status_id, offered_at, expires_at
            ) VALUES (
                :aid, :bid, :pid,
                (SELECT id FROM status_types WHERE domain='assignment' AND code='offered'),
                now(), now() + interval '5 min'
            )
            """
        ),
        {"aid": aid, "bid": bid, "pid": pid},
    )
    pay_id = uniq.id()
    await session.execute(
        text(
            """
            INSERT INTO payments (
                id, booking_id, amount, idempotency_key, gateway_txn_id, status, created_at
            ) VALUES (:pid, :bid, 2100, :key, :gw, 'success', now())
            """
        ),
        {"pid": pay_id, "bid": bid, "key": f"idem-{uniq.id()}", "gw": f"pay_{uniq.id()}"},
    )
    actor = await _mk_admin(session)
    await session.commit()

    detail = await bookings_ep.get_booking_detail(
        uuid.UUID(bid), _FakeRequest(), _admin(actor), session
    )
    await session.commit()
    assert detail.status == "requested"
    assert detail.customer.phone == phone
    assert detail.puja_name == "Test Puja"
    assert detail.address.area_label is not None
    assert len(detail.assignments) == 1
    assert detail.assignments[0].status == "offered"
    assert len(detail.payments) == 1
    assert detail.payments[0].status == "success"
    assert detail.dispatch.dispatch_mode == "broadcast"

    audit = (
        await session.execute(
            text(
                "SELECT action, entity_id FROM admin_audit_log "
                "WHERE actor_user_id = :uid AND entity_id = :bid"
            ),
            {"uid": str(actor), "bid": bid},
        )
    ).mappings().first()
    assert audit is not None
    assert audit["action"] == "read"


@pytest.mark.asyncio
async def test_booking_detail_not_found(session, seed):
    actor = await _mk_admin(session)
    await session.commit()
    with pytest.raises(HTTPException) as exc:
        await bookings_ep.get_booking_detail(
            uuid.uuid4(), _FakeRequest(), _admin(actor), session
        )
    assert exc.value.status_code == 404
