"""
Offer accept / reject (spec API_CONTRACTS pujari app, DISPATCH_FLOW step 6).

ACCEPT: ONE UPDATE setting status_id=(assignment, accepted) AND responded_at=now.
Trigger 3 assigns the booking and flips to confirmed. Then assign RM (§21.4) in the
same transaction — the only app-layer write after accept.
DB errors surface to the shared handler (409/410 per API_CONTRACTS).

REJECT: ONE UPDATE to rejected + responded_at; then inline fast-path — if the
booking now has zero live offers, enqueue rebroadcast immediately (idempotent).
"""
from __future__ import annotations

import uuid

import structlog
from fastapi import HTTPException, status as http
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import BookingAssignment
from app.models.catalog import Pujari
from app.services import booking_events
from app.services.relationship_manager import assign_rm_on_confirm
from app.services.status import status_id
from app.services.slot_guard import assert_slot_not_past_for_accept
from app.services.travel_buffer import assert_accept_travel_buffer_ok

log = structlog.get_logger()


async def _assignment_owned_by(
    db: AsyncSession, assignment_id: uuid.UUID, user_id: uuid.UUID
) -> BookingAssignment:
    assignment = (
        await db.execute(
            select(BookingAssignment).where(BookingAssignment.id == assignment_id)
        )
    ).scalar_one_or_none()
    if assignment is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "Offer not found.")
    pujari_user = (
        await db.execute(select(Pujari.user_id).where(Pujari.id == assignment.pujari_id))
    ).scalar_one_or_none()
    if pujari_user != user_id:
        raise HTTPException(http.HTTP_403_FORBIDDEN, "Not your offer.")
    return assignment


async def accept_offer(
    db: AsyncSession, *, user_id: uuid.UUID, assignment_id: uuid.UUID
) -> dict:
    assignment = await _assignment_owned_by(db, assignment_id, user_id)
    accepted_id = await status_id(db, "assignment", "accepted")
    await assert_slot_not_past_for_accept(db, booking_id=assignment.booking_id)
    await assert_accept_travel_buffer_ok(
        db, pujari_id=assignment.pujari_id, booking_id=assignment.booking_id
    )
    # ONE UPDATE. Trigger 3 fires on this UPDATE and does the rest (or raises,
    # which the shared handler maps to 409/410).
    await db.execute(
        text(
            "UPDATE booking_assignments SET status_id = :sid, responded_at = now() "
            "WHERE id = :aid"
        ),
        {"sid": accepted_id, "aid": str(assignment_id)},
    )
    await assign_rm_on_confirm(db, assignment.booking_id)
    booking_class = (
        await db.execute(
            text("SELECT booking_class FROM bookings WHERE id = :bid"),
            {"bid": str(assignment.booking_id)},
        )
    ).scalar_one_or_none()
    if booking_class == "advance":
        from app.workers.celery_app import celery_app

        celery_app.send_task(
            "app.workers.notifications.notify_accept_ack",
            args=[str(assignment.booking_id), str(user_id)],
        )
    log.info("offer_accepted", assignment_id=str(assignment_id), booking_id=str(assignment.booking_id))
    await booking_events.publish_booking_event(
        str(assignment.booking_id), "status_changed", status="confirmed"
    )
    return {"status": "accepted", "booking_id": str(assignment.booking_id)}


async def reject_offer(
    db: AsyncSession, *, user_id: uuid.UUID, assignment_id: uuid.UUID
) -> dict:
    assignment = await _assignment_owned_by(db, assignment_id, user_id)
    rejected_id = await status_id(db, "assignment", "rejected")
    await db.execute(
        text(
            "UPDATE booking_assignments SET status_id = :sid, responded_at = now() "
            "WHERE id = :aid AND responded_at IS NULL"
        ),
        {"sid": rejected_id, "aid": str(assignment_id)},
    )

    # fast-path: zero live offers left? enqueue rebroadcast now (idempotent).
    live = (
        await db.execute(
            text(
                "SELECT count(*) FROM booking_assignments "
                "WHERE booking_id = :bid AND responded_at IS NULL"
            ),
            {"bid": str(assignment.booking_id)},
        )
    ).scalar_one()
    enqueue = None
    if live == 0:
        enqueue = str(assignment.booking_id)
    log.info("offer_rejected", assignment_id=str(assignment_id), enqueue_rebroadcast=enqueue)
    return {"status": "rejected", "enqueue_rebroadcast": enqueue}
