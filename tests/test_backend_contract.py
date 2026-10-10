"""Backend contract §23 — app-config, booking_class, catalog flag, reconfirm, panchangam."""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.api.v1.endpoints import app_config as app_config_ep
from app.api.v1.endpoints import bookings as bookings_ep
from app.api.v1.endpoints import catalog as catalog_ep
from app.api.v1.endpoints import panchangam as panchangam_ep
from app.api.v1.endpoints import pujari_bookings as pujari_bookings_ep
from app.core.dependencies import Principal
from app.services.pujari_reconfirm import pujari_reconfirm_booking

CUSTOMER = "aaaaaaaa-0000-0000-0000-000000000001"
PUJARI_USER = "bbbbbbbb-0000-0000-0000-000000000001"
ADDRESS = "dddddddd-0000-0000-0000-000000000001"
PUJA = "11111111-1111-1111-1111-111111111111"


def _customer(uid: uuid.UUID | str = CUSTOMER) -> Principal:
    return Principal(user_id=uuid.UUID(str(uid)), app_context="customer", roles=())


def _pujari(uid: uuid.UUID | str = PUJARI_USER) -> Principal:
    return Principal(user_id=uuid.UUID(str(uid)), app_context="pujari", roles=())


async def _pujari_id(session, user_id: str = PUJARI_USER) -> str:
    return (
        await session.execute(
            text("SELECT id::text FROM pujaris WHERE user_id = :u"),
            {"u": user_id},
        )
    ).scalar_one()


@pytest.mark.asyncio
async def test_app_config_public_read(session):
    resp = await app_config_ep.get_app_config(db=session)
    assert isinstance(resp.night_bookings_enabled, bool)
    assert resp.instant_lead_hours >= 1
    assert resp.advance_booking_amount == Decimal(str(resp.advance_booking_amount))
    assert isinstance(resp.payments_enabled, bool)
    assert isinstance(resp.tds_accrual_enabled, bool)
    assert isinstance(resp.pujari_fy_pan_gate_enabled, bool)
    assert isinstance(resp.setu_pan_verify_configured, bool)
    if resp.payments_enabled:
        assert resp.razorpay_key_id and resp.razorpay_key_id.startswith("rzp_")


@pytest.mark.asyncio
async def test_list_pujas_includes_is_muhurat_bound(session):
    customer_id = uuid.uuid4()
    await session.execute(
        text("INSERT INTO users (id, full_name, phone) VALUES (:id, 'C', :ph)"),
        {"id": str(customer_id), "ph": "+91985" + uuid.uuid4().hex[:7]},
    )
    await session.commit()

    resp = await catalog_ep.list_pujas(limit=20, _p=_customer(customer_id), db=session)
    assert resp.pujas
    assert hasattr(resp.pujas[0], "is_muhurat_bound")


@pytest.mark.asyncio
async def test_list_bookings_includes_booking_class(session, seed):
    resp = await bookings_ep.list_bookings(p=_customer(), limit=20, db=session)
    if resp["bookings"]:
        assert "booking_class" in resp["bookings"][0]


@pytest.mark.asyncio
async def test_panchangam_cache_hit_and_miss(session):
    target = dt.date(2099, 1, 15)
    fetched = dt.datetime(2099, 1, 14, 6, 0, tzinfo=dt.UTC)
    await session.execute(
        text(
            """
            INSERT INTO panchangam_daily (
                city, panchang_date, locale, panchang_system,
                vaaram, tithi, nakshatram, sunrise, sunset, fetched_at
            ) VALUES (
                'Hyderabad', :d, 'te', 'drik',
                'సోమవారం', 'శుక్ల పక్షం', 'రోహిణి',
                '2099-01-15T06:42:00+05:30', '2099-01-15T18:10:00+05:30', :fetched
            )
            ON CONFLICT (city, panchang_date, locale, panchang_system) DO UPDATE
            SET vaaram = EXCLUDED.vaaram,
                tithi = EXCLUDED.tithi,
                nakshatram = EXCLUDED.nakshatram,
                sunrise = EXCLUDED.sunrise,
                sunset = EXCLUDED.sunset,
                fetched_at = EXCLUDED.fetched_at
            """
        ),
        {"d": target, "fetched": fetched},
    )
    await session.commit()

    hit = await panchangam_ep.get_panchangam(
        city="Hyderabad",
        date=target,
        locale="te",
        panchang_system="drik",
        db=session,
    )
    assert hit.tithi == "శుక్ల పక్షం"
    assert hit.nakshatram == "రోహిణి"
    assert hit.vaaram == "సోమవారం"
    assert hit.sunrise == "2099-01-15T06:42:00+05:30"
    assert hit.sunset == "2099-01-15T18:10:00+05:30"

    miss_date = dt.date(2099, 1, 16)
    await session.execute(
        text(
            "DELETE FROM panchangam_daily WHERE city = 'Hyderabad' "
            "AND panchang_date = :d AND locale = 'te'"
        ),
        {"d": miss_date},
    )
    await session.commit()

    with pytest.raises(HTTPException) as exc:
        await panchangam_ep.get_panchangam(
            city="Hyderabad",
            date=miss_date,
            locale="te",
            panchang_system="drik",
            db=session,
        )
    assert exc.value.status_code == 404


def _unique_slot_time(uniq) -> str:
    h = (int(uniq.id().replace("-", "")[:4], 16) % 12) + 8
    m = int(uniq.id().replace("-", "")[4:8], 16) % 60
    return f"{h:02d}:{m:02d}:00"


@pytest.mark.asyncio
async def test_pujari_reconfirm_idempotent(session, uniq):
    bid = uniq.id()
    pid = await _pujari_id(session)
    slot_time = _unique_slot_time(uniq)
    confirmed_id = (
        await session.execute(
            text(
                "SELECT id FROM status_types WHERE domain='booking' AND code='confirmed'"
            )
        )
    ).scalar_one()
    policy_id = (
        await session.execute(
            text("SELECT id FROM cancellation_policies WHERE name='standard'")
        )
    ).scalar_one()
    ping_at = dt.datetime.now(dt.UTC) - dt.timedelta(hours=1)

    await session.execute(
        text(
            """
            INSERT INTO bookings (
                id, user_id, pujari_id, puja_id, address_id, status_id,
                cancellation_policy_id, scheduled_date, scheduled_time,
                duration_minutes, total_amount, amount_due_online, amount_due_offline,
                payment_mode, paid_at, dispatch_mode, booking_class, created_at, updated_at
            ) VALUES (
                :bid, :uid, :pid, :puja, :addr, :st,
                :policy, CURRENT_DATE + 2, CAST(:slot_time AS time), 90,
                2100, 2100, 0, 'full_online', now(), 'broadcast', 'advance', now(), now()
            )
            """
        ),
        {
            "bid": bid,
            "uid": CUSTOMER,
            "pid": pid,
            "puja": PUJA,
            "addr": ADDRESS,
            "st": confirmed_id,
            "policy": policy_id,
            "slot_time": slot_time,
        },
    )
    await session.execute(
        text(
            "INSERT INTO booking_reconfirmations (booking_id, ping_sent_at) "
            "VALUES (:bid, :ping)"
        ),
        {"bid": bid, "ping": ping_at},
    )
    await session.commit()

    first = await pujari_reconfirm_booking(
        session,
        user_id=uuid.UUID(PUJARI_USER),
        booking_id=uuid.UUID(bid),
    )
    assert first["already_confirmed"] is False
    assert first["pujari_confirmed_at"] is not None

    second = await pujari_reconfirm_booking(
        session,
        user_id=uuid.UUID(PUJARI_USER),
        booking_id=uuid.UUID(bid),
    )
    assert second["already_confirmed"] is True
    assert second["pujari_confirmed_at"] == first["pujari_confirmed_at"]

    via_http = await pujari_bookings_ep.reconfirm_booking(
        uuid.UUID(bid), _pujari(), session
    )
    assert via_http.already_confirmed is True
