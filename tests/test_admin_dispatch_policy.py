"""Admin dispatch policy settings (A-DISPATCH-POLICY)."""
from __future__ import annotations

import json
import uuid

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import text

from app.api.v1.endpoints import admin as admin_ep
from app.core.dependencies import Principal
from app.schemas.admin import DispatchPolicyUpdate
from app.services.dispatch_launch import load_dispatch_settings_async


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
        {"id": str(uid), "ph": "+91972" + uuid.uuid4().hex[:7]},
    )
    return uid


@pytest.mark.asyncio
async def test_get_dispatch_policy_matches_worker_loader(session, seed):
    actor = await _mk_admin(session)
    await session.commit()
    resp = await admin_ep.get_dispatch_policy(_admin(actor), session)
    launch = await load_dispatch_settings_async(session)
    assert resp.immediate_dispatch_on_payment == launch.immediate_dispatch_on_payment
    assert resp.instant_lead_hours == launch.instant_lead_hours
    assert resp.dispatch_buffer_minutes == launch.dispatch_buffer_minutes
    assert resp.reconfirm_quiet_hours_start == "22:00"


@pytest.mark.asyncio
async def test_support_can_read_dispatch_policy(session, seed):
    actor = await _mk_admin(session)
    await session.commit()
    resp = await admin_ep.get_dispatch_policy(_support(actor), session)
    assert resp.dispatch_buffer_minutes == 60


@pytest.mark.asyncio
async def test_admin_updates_immediate_dispatch(session, seed):
    actor = await _mk_admin(session)
    await session.execute(
        text(
            """
            INSERT INTO platform_settings (key, value_json, updated_at)
            VALUES ('immediate_dispatch_on_payment', 'false'::jsonb, now())
            ON CONFLICT (key) DO UPDATE SET value_json = 'false'::jsonb
            """
        )
    )
    await session.commit()

    current = await admin_ep.get_dispatch_policy(_admin(actor), session)
    assert current.immediate_dispatch_on_payment is False

    updated = await admin_ep.set_dispatch_policy(
        DispatchPolicyUpdate(
            instant_lead_hours=current.instant_lead_hours,
            instant_dispatch_minutes=current.instant_dispatch_minutes,
            advance_dispatch_start_hours=current.advance_dispatch_start_hours,
            advance_dispatch_fail_hours=current.advance_dispatch_fail_hours,
            reoffer_cooldown_minutes=current.reoffer_cooldown_minutes,
            dispatch_buffer_minutes=current.dispatch_buffer_minutes,
            immediate_dispatch_on_payment=True,
            instant_offer_ttl_seconds=current.instant_offer_ttl_seconds,
            advance_offer_ttl_hours=current.advance_offer_ttl_hours,
            max_live_advance_offers_per_pujari=current.max_live_advance_offers_per_pujari,
            rm_escalation_hours_no_accept=current.rm_escalation_hours_no_accept,
            rm_escalation_t24_hours=current.rm_escalation_t24_hours,
            night_bookings_enabled=current.night_bookings_enabled,
            reconfirm_quiet_hours_start=current.reconfirm_quiet_hours_start,
            reconfirm_quiet_hours_end=current.reconfirm_quiet_hours_end,
            change_reason="launch posture",
        ),
        _FakeRequest(),
        _admin(actor),
        session,
    )
    assert updated.immediate_dispatch_on_payment is True

    launch = await load_dispatch_settings_async(session)
    assert launch.immediate_dispatch_on_payment is True

    audit = (
        await session.execute(
            text(
                """
                SELECT action, entity_id FROM admin_audit_log
                WHERE entity_type = 'platform_settings' AND entity_id = 'dispatch_policy'
                ORDER BY created_at DESC LIMIT 1
                """
            )
        )
    ).first()
    assert audit is not None
    assert audit[0] == "update"


def _update_from(current, **overrides) -> DispatchPolicyUpdate:
    fields = {
        "instant_lead_hours": current.instant_lead_hours,
        "instant_dispatch_minutes": current.instant_dispatch_minutes,
        "advance_dispatch_start_hours": current.advance_dispatch_start_hours,
        "advance_dispatch_fail_hours": current.advance_dispatch_fail_hours,
        "reoffer_cooldown_minutes": current.reoffer_cooldown_minutes,
        "dispatch_buffer_minutes": current.dispatch_buffer_minutes,
        "immediate_dispatch_on_payment": current.immediate_dispatch_on_payment,
        "instant_offer_ttl_seconds": current.instant_offer_ttl_seconds,
        "advance_offer_ttl_hours": current.advance_offer_ttl_hours,
        "max_live_advance_offers_per_pujari": current.max_live_advance_offers_per_pujari,
        "rm_escalation_hours_no_accept": current.rm_escalation_hours_no_accept,
        "rm_escalation_t24_hours": current.rm_escalation_t24_hours,
        "night_bookings_enabled": current.night_bookings_enabled,
        "reconfirm_quiet_hours_start": current.reconfirm_quiet_hours_start,
        "reconfirm_quiet_hours_end": current.reconfirm_quiet_hours_end,
    }
    fields.update(overrides)
    return DispatchPolicyUpdate(**fields)


@pytest.mark.asyncio
async def test_admin_sets_max_offer_rounds_and_omission_keeps_it(session, seed):
    actor = await _mk_admin(session)
    await session.commit()
    original = (
        await session.execute(
            text("SELECT value_json FROM platform_settings WHERE key = 'max_offer_rounds'")
        )
    ).scalar_one_or_none()
    try:
        current = await admin_ep.get_dispatch_policy(_admin(actor), session)
        updated = await admin_ep.set_dispatch_policy(
            _update_from(current, max_offer_rounds=3), _FakeRequest(), _admin(actor), session
        )
        await session.commit()
        assert updated.max_offer_rounds == 3
        assert (await load_dispatch_settings_async(session)).max_offer_rounds == 3

        kept = await admin_ep.set_dispatch_policy(
            _update_from(updated), _FakeRequest(), _admin(actor), session
        )
        await session.commit()
        assert kept.max_offer_rounds == 3
    finally:
        if original is None:
            await session.execute(text("DELETE FROM platform_settings WHERE key = 'max_offer_rounds'"))
        else:
            await session.execute(
                text("UPDATE platform_settings SET value_json = CAST(:v AS jsonb) WHERE key = 'max_offer_rounds'"),
                {"v": json.dumps(original)},
            )
        await session.commit()


@pytest.mark.asyncio
async def test_admin_rejects_escalation_lead_lte_fail_hours(session, seed):
    from app.services.admin_dispatch_policy import (
        DispatchPolicyView,
        fetch_dispatch_policy,
        persist_dispatch_policy,
    )

    actor = await _mk_admin(session)
    await session.commit()
    current = await fetch_dispatch_policy(session)
    bad = DispatchPolicyView(
        instant_lead_hours=current.instant_lead_hours,
        instant_dispatch_minutes=current.instant_dispatch_minutes,
        advance_dispatch_start_hours=current.advance_dispatch_start_hours,
        advance_dispatch_fail_hours=current.advance_dispatch_fail_hours,
        reoffer_cooldown_minutes=current.reoffer_cooldown_minutes,
        dispatch_buffer_minutes=current.dispatch_buffer_minutes,
        immediate_dispatch_on_payment=current.immediate_dispatch_on_payment,
        instant_offer_ttl_seconds=current.instant_offer_ttl_seconds,
        advance_offer_ttl_hours=current.advance_offer_ttl_hours,
        max_live_advance_offers_per_pujari=current.max_live_advance_offers_per_pujari,
        rm_escalation_hours_no_accept=current.rm_escalation_hours_no_accept,
        rm_escalation_t24_hours=current.rm_escalation_t24_hours,
        max_offer_rounds=current.max_offer_rounds,
        urgency_escalation_lead_hours=current.advance_dispatch_fail_hours,
        escalated_offer_ttl_seconds=current.escalated_offer_ttl_seconds,
        rebroadcast_on_urgency_flip=current.rebroadcast_on_urgency_flip,
        night_bookings_enabled=current.night_bookings_enabled,
        reconfirm_quiet_hours_start=current.reconfirm_quiet_hours_start,
        reconfirm_quiet_hours_end=current.reconfirm_quiet_hours_end,
    )
    with pytest.raises(HTTPException) as exc:
        await persist_dispatch_policy(session, bad)
    assert exc.value.status_code == 422


def test_max_offer_rounds_rejects_negative():
    with pytest.raises(ValidationError) as exc:
        DispatchPolicyUpdate.model_validate({"max_offer_rounds": -1})
    assert any(
        err["loc"] == ("max_offer_rounds",) and err["type"] == "greater_than_equal"
        for err in exc.value.errors()
    )


@pytest.mark.asyncio
async def test_migration_039_posture_update_restores_immediate(session, seed):
    await session.execute(
        text(
            """
            UPDATE platform_settings
            SET value_json = 'false'::jsonb
            WHERE key = 'immediate_dispatch_on_payment'
            """
        )
    )
    await session.execute(
        text(
            """
            UPDATE platform_settings
            SET value_json = 'true'::jsonb,
                updated_at = now()
            WHERE key = 'immediate_dispatch_on_payment'
              AND value_json = 'false'::jsonb
            """
        )
    )
    await session.commit()
    launch = await load_dispatch_settings_async(session)
    assert launch.immediate_dispatch_on_payment is True