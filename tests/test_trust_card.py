"""Trust card Slice A — feature flag, customer booking payload, public name admin."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.api.v1.endpoints import admin_kyc as admin_kyc_ep
from app.api.v1.endpoints import bookings as bookings_ep
from app.api.v1.endpoints import me_profile as me_ep
from app.core.dependencies import Principal
from app.schemas.admin_kyc import PublicNameApproveRequest
from app.services.trust_card import customer_display_name, normalize_public_name_candidate

CUSTOMER = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
PUJARI_USER = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000001")
PUJARI = uuid.UUID("cccccccc-0000-0000-0000-000000000001")
ADDRESS = "dddddddd-0000-0000-0000-000000000001"
PUJA = "11111111-1111-1111-1111-111111111111"


class _FakeRequest:
    client = None


def _customer() -> Principal:
    return Principal(user_id=CUSTOMER, app_context="customer", roles=())


def _pujari() -> Principal:
    return Principal(user_id=PUJARI_USER, app_context="pujari", roles=())


async def _mk_admin(session) -> uuid.UUID:
    uid = uuid.uuid4()
    await session.execute(
        text("INSERT INTO users (id, full_name, phone) VALUES (:id, 'Admin', :ph)"),
        {"id": str(uid), "ph": "+91974" + uuid.uuid4().hex[:7]},
    )
    return uid


def _admin(uid: uuid.UUID) -> Principal:
    return Principal(user_id=uid, app_context="admin", roles=("admin",))


async def _set_trust_flag(session, enabled: bool) -> None:
    await session.execute(
        text(
            """
            INSERT INTO platform_settings (key, value_json, updated_at)
            VALUES ('feature_trust_card_enabled', CAST(:val AS jsonb), now())
            ON CONFLICT (key) DO UPDATE SET value_json = EXCLUDED.value_json, updated_at = now()
            """
        ),
        {"val": '{"enabled": true}' if enabled else '{"enabled": false}'},
    )


async def _make_requested_booking_with_offer(
    session, uniq, *, slot_time: str = "09:30"
) -> tuple[str, str]:
    bid, aid = str(uuid.uuid4()), str(uuid.uuid4())
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
            "uid": str(CUSTOMER),
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
                id, booking_id, pujari_id, status_id, offered_at, expires_at
            ) VALUES (
                :aid, :bid, :pid,
                (SELECT id FROM status_types WHERE domain='assignment' AND code='offered'),
                now(), now() + interval '2 min'
            )
            """
        ),
        {"aid": aid, "bid": bid, "pid": str(PUJARI)},
    )
    return bid, aid


async def _accept_assignment(session, aid: str) -> None:
    await session.execute(
        text(
            """
            UPDATE booking_assignments
            SET status_id = (
                SELECT id FROM status_types WHERE domain='assignment' AND code='accepted'
            ),
            responded_at = now()
            WHERE id = :aid
            """
        ),
        {"aid": aid},
    )


def test_normalize_public_name_skips_placeholder():
    assert normalize_public_name_candidate("New User") is None
    assert normalize_public_name_candidate("  Rama Sharma  ") == "Rama Sharma"


def test_customer_display_name_fallback():
    assert customer_display_name(None) == "Your pujari"
    assert customer_display_name("Rama Sharma") == "Rama Sharma"


@pytest.mark.asyncio
async def test_trust_card_flag_off_keeps_legacy_pujari(session, seed, uniq):
    await _set_trust_flag(session, False)
    bid, aid = await _make_requested_booking_with_offer(session, uniq)
    await _accept_assignment(session, aid)
    await session.commit()

    detail = await bookings_ep.get_booking(uuid.UUID(bid), _customer(), session)
    assert detail["pujari"] is not None
    assert "full_name" in detail["pujari"]
    assert "id" in detail["pujari"]
    assert "display_name" not in detail["pujari"]


@pytest.mark.asyncio
async def test_trust_card_flag_on_hides_pii(session, seed, uniq):
    await _set_trust_flag(session, True)
    await session.execute(
        text(
            "UPDATE pujaris SET public_name = :name, verification_status = 'verified' "
            "WHERE id = :pid"
        ),
        {"pid": str(PUJARI), "name": "Sharma Ji"},
    )
    bid, aid = await _make_requested_booking_with_offer(session, uniq, slot_time="09:45")
    await _accept_assignment(session, aid)
    await session.commit()

    detail = await bookings_ep.get_booking(uuid.UUID(bid), _customer(), session)
    pujari = detail["pujari"]
    assert pujari is not None
    assert "full_name" not in pujari
    assert "id" not in pujari
    assert pujari["display_name"] == "Sharma Ji"
    assert pujari["identity_verified"] is True
    assert pujari["public_name_ops_approved"] is False
    assert pujari["trusted_on_platform"] is False
    assert pujari["assignment_version"] >= 1


@pytest.mark.asyncio
async def test_trust_card_flag_on_presigned_profile_photo_when_pointer_set(
    session, seed, uniq, monkeypatch
):
    """Slice B: admin-published photo doc → customer payload may include presigned URL."""
    await _set_trust_flag(session, True)
    doc_id = uuid.uuid4()
    await session.execute(
        text(
            """
            INSERT INTO pujari_documents (
                id, pujari_id, doc_type, file_url, version, is_current, status, uploaded_at
            ) VALUES (
                :did, :pid, 'photo', 'kyc/917000000011/photo/approved.jpg', 1, true, 'verified', now()
            )
            """
        ),
        {"did": str(doc_id), "pid": str(PUJARI)},
    )
    await session.execute(
        text(
            "UPDATE pujaris SET customer_profile_photo_doc_id = :did, "
            "public_name = :name, verification_status = 'verified' WHERE id = :pid"
        ),
        {"did": str(doc_id), "pid": str(PUJARI), "name": "Sharma Ji"},
    )
    bid, aid = await _make_requested_booking_with_offer(session, uniq, slot_time="14:00")
    await _accept_assignment(session, aid)
    await session.commit()

    monkeypatch.setattr(
        "app.services.trust_card.presign_profile_photo_file_url",
        lambda _url: ("https://signed.example/p.jpg", 3600),
    )

    detail = await bookings_ep.get_booking(uuid.UUID(bid), _customer(), session)
    pu = detail["pujari"]
    assert pu["profile_photo_url"] == "https://signed.example/p.jpg"
    assert pu["profile_photo_url_expires_in"] == 3600


@pytest.mark.asyncio
async def test_profile_photo_pointer_sync_verified_then_rejected(session, seed):
    """Admin review of `photo` doc sets then clears `customer_profile_photo_doc_id`."""
    from app.services.profile_photo_publish import sync_pujari_customer_profile_photo_pointer

    doc_id = uuid.uuid4()
    await session.execute(
        text(
            """
            INSERT INTO pujari_documents (
                id, pujari_id, doc_type, file_url, version, is_current, status, uploaded_at
            ) VALUES (
                :did, :pid, 'photo', 'kyc/917000000011/photo/v1.jpg', 1, true, 'verified', now()
            )
            """
        ),
        {"did": str(doc_id), "pid": str(PUJARI)},
    )
    await session.commit()

    async with session.begin():
        await sync_pujari_customer_profile_photo_pointer(
            session,
            pujari_id=PUJARI,
            document_id=doc_id,
            doc_type="photo",
            new_status="verified",
        )
    row = (
        await session.execute(
            text("SELECT customer_profile_photo_doc_id FROM pujaris WHERE id = :pid"),
            {"pid": str(PUJARI)},
        )
    ).one()
    assert str(row[0]) == str(doc_id)

    async with session.begin():
        await sync_pujari_customer_profile_photo_pointer(
            session,
            pujari_id=PUJARI,
            document_id=doc_id,
            doc_type="photo",
            new_status="rejected",
        )
    row2 = (
        await session.execute(
            text("SELECT customer_profile_photo_doc_id FROM pujaris WHERE id = :pid"),
            {"pid": str(PUJARI)},
        )
    ).one()
    assert row2[0] is None


@pytest.mark.asyncio
async def test_trust_card_flag_on_falls_back_to_full_name_when_no_public_name(session, seed, uniq):
    """Verified pujari with no approved public_name still shows a real label (not the generic fallback)."""
    await _set_trust_flag(session, True)
    await session.execute(
        text("UPDATE users SET full_name = :name WHERE id = :uid"),
        {"uid": str(PUJARI_USER), "name": "M Venkata Sai Krishna"},
    )
    await session.execute(
        text(
            "UPDATE pujaris SET public_name = NULL, public_name_pending = NULL, "
            "verification_status = 'verified' WHERE id = :pid"
        ),
        {"pid": str(PUJARI)},
    )
    bid, aid = await _make_requested_booking_with_offer(session, uniq, slot_time="10:15")
    await _accept_assignment(session, aid)
    await session.commit()

    detail = await bookings_ep.get_booking(uuid.UUID(bid), _customer(), session)
    pujari = detail["pujari"]
    assert pujari is not None
    assert pujari["display_name"] == "M Venkata Sai Krishna"
    assert pujari["identity_verified"] is True


@pytest.mark.asyncio
async def test_trust_card_flag_on_no_full_name_when_public_hidden(session, seed, uniq):
    """When public name is hidden from customers, do not fall back to legal full_name."""
    await _set_trust_flag(session, True)
    await session.execute(
        text("UPDATE users SET full_name = :name WHERE id = :uid"),
        {"uid": str(PUJARI_USER), "name": "Secret Legal Name"},
    )
    await session.execute(
        text(
            "UPDATE pujaris SET public_name = NULL, public_name_pending = NULL, "
            "public_name_visible = false, verification_status = 'verified' "
            "WHERE id = :pid"
        ),
        {"pid": str(PUJARI)},
    )
    bid, aid = await _make_requested_booking_with_offer(session, uniq, slot_time="11:00")
    await _accept_assignment(session, aid)
    await session.commit()

    detail = await bookings_ep.get_booking(uuid.UUID(bid), _customer(), session)
    assert detail["pujari"]["display_name"] == "Your pujari"


@pytest.mark.asyncio
async def test_get_me_partner_block(session, seed):
    await _set_trust_flag(session, False)
    await session.commit()
    me = await me_ep.get_me(_pujari(), session)
    assert me.app_context == "pujari"
    assert me.partner is not None
    assert me.partner.pujari_id == PUJARI
    assert me.partner.trust_card_enabled is False
    assert me.partner.profile_photo_url is None


@pytest.mark.asyncio
async def test_trusted_on_platform_when_ops_approved_public_name(session, seed, uniq):
    await _set_trust_flag(session, True)
    await session.execute(
        text(
            """
            UPDATE pujaris
            SET public_name = 'Trusted Name',
                public_name_pending = NULL,
                public_name_approved_at = now(),
                public_name_visible = true,
                verification_status = 'verified'
            WHERE id = :pid
            """
        ),
        {"pid": str(PUJARI)},
    )
    bid, aid = await _make_requested_booking_with_offer(session, uniq, slot_time="09:50")
    await _accept_assignment(session, aid)
    await session.commit()

    detail = await bookings_ep.get_booking(uuid.UUID(bid), _customer(), session)
    pu = detail["pujari"]
    assert pu["identity_verified"] is True
    assert pu["public_name_ops_approved"] is True
    assert pu["trusted_on_platform"] is True
    assert pu["display_name"] == "Trusted Name"


@pytest.mark.asyncio
async def test_admin_approve_public_name(session, seed):
    await session.execute(
        text(
            """
            UPDATE pujaris
            SET public_name_pending = 'Govind Sharma', verification_status = 'verified'
            WHERE id = :pid
            """
        ),
        {"pid": str(PUJARI)},
    )
    await session.commit()

    admin_user = await _mk_admin(session)
    await session.commit()

    resp = await admin_kyc_ep.approve_public_name(
        PUJARI,
        PublicNameApproveRequest(change_reason="QA"),
        _FakeRequest(),
        _admin(admin_user),
        session,
    )
    assert resp.public_name == "Govind Sharma"
    row = (
        await session.execute(
            text("SELECT public_name, public_name_pending FROM pujaris WHERE id = :pid"),
            {"pid": str(PUJARI)},
        )
    ).one()
    assert row[0] == "Govind Sharma"
    assert row[1] is None
