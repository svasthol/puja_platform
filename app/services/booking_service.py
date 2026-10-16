"""
Booking creation — the one-transaction checkout flow (spec DISPATCH_FLOW step 2,
API_CONTRACTS POST /v1/bookings).

Order of operations (all in ONE transaction; caller uses get_db_txn):
  a. SELECT hold FOR UPDATE — owner + unexpired, else 410.
  b. Compute total_amount (puja + addons), snapshot booking_fee split.
  c. INSERT booking row BEFORE the Razorpay call so ux_bookings_no_duplicate_submit
     fires early (idempotent create) and we never mint an orphan order for a dup.
     Uses PostgreSQL ON CONFLICT DO NOTHING on the partial unique index (same
     guarantee as SAVEPOINT flush, without aborting the outer transaction).
  d. Create Razorpay order for booking_fee ONLY. Failure -> full rollback.
  e. Persist razorpay_order_id on the booking; EXTEND hold to now()+15min.

NEVER writes bookings.pujari_id (trigger-managed). NEVER inserts assignments here.
"""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import structlog
from fastapi import HTTPException, status as http
from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import DuplicateBookingSubmit
from app.models.booking import Booking, BookingAddon, SlotHold
from app.models.catalog import Puja, PujaAddon
from app.models.lookups import CancellationPolicy
from app.schemas.booking import BookingCreate, BookingCreateResponse
from app.services import razorpay_client
from app.services.booking_gate import assert_booking_gate, load_booking_gate_settings
from app.services.dispatch_supply import assert_dispatch_supply
from app.services.pricing import (
    BOOKING_FEE_LABEL,
    compute_booking_fee_amounts,
    load_booking_fee,
)
from app.services.status import status_id

log = structlog.get_logger()
_settings = get_settings()
_LAUNCH_MODE = "booking_fee"


async def compute_amounts(
    db: AsyncSession,
    *,
    puja_id: uuid.UUID,
    pujari_id: uuid.UUID | None,
    addon_prices: list[Decimal],
    promo_pct: int,
    payment_mode: str,
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """Returns (total_amount, amount_due_online, amount_due_offline, booking_fee)."""
    from app.services.pricing_resolver import resolve_puja_unit_price

    if promo_pct and _settings.FULL_ONLINE_ENABLED is False:
        raise HTTPException(
            http.HTTP_422_UNPROCESSABLE_ENTITY,
            "Promo codes are not available at launch.",
        )

    unit = await resolve_puja_unit_price(db, puja_id, pujari_id)
    subtotal = unit + sum(addon_prices, Decimal("0"))
    if promo_pct:
        subtotal = (subtotal * (Decimal(100 - promo_pct) / Decimal(100))).quantize(
            Decimal("0.01")
        )
    total = subtotal

    if payment_mode == _LAUNCH_MODE or not _settings.FULL_ONLINE_ENABLED:
        fee = await load_booking_fee(db)
        return compute_booking_fee_amounts(total, fee)

    if payment_mode == "full_online":
        return total, total, Decimal("0"), Decimal("0")

    from app.models.lookups import PlatformSetting

    row = (
        await db.execute(
            select(PlatformSetting.value_json).where(
                PlatformSetting.key == "advance_booking_amount"
            )
        )
    ).scalar_one_or_none()
    if not row:
        raise RuntimeError("Seed data missing: platform_settings.advance_booking_amount")
    advance = Decimal(str(row["amount"]))
    online = min(advance, total)
    return total, online, total - online, Decimal("0")


def _assert_launch_payment_mode(payment_mode: str) -> str:
    if not _settings.FULL_ONLINE_ENABLED:
        if payment_mode != _LAUNCH_MODE:
            raise HTTPException(
                http.HTTP_422_UNPROCESSABLE_ENTITY,
                "Only booking_fee checkout is available at launch.",
            )
        return _LAUNCH_MODE
    if payment_mode not in ("full_online", "advance_balance", _LAUNCH_MODE):
        raise HTTPException(http.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid payment mode.")
    return payment_mode


async def _validate_promo(
    db: AsyncSession, code: str, now: dt.datetime
) -> tuple[uuid.UUID, int, int]:
    """Returns (promo_code_id, discount_pct, max_uses_per_user); 422 if invalid."""
    if not _settings.FULL_ONLINE_ENABLED:
        raise HTTPException(
            http.HTTP_422_UNPROCESSABLE_ENTITY,
            "Promo codes are not available at launch.",
        )
    row = (
        await db.execute(
            text(
                "SELECT id, discount_pct, max_uses_per_user FROM promo_codes "
                "WHERE code = :code AND is_active "
                "AND valid_from <= :now AND valid_until >= :now"
            ),
            {"code": code, "now": now},
        )
    ).mappings().first()
    if row is None:
        raise HTTPException(http.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid or expired promo code.")
    return row["id"], row["discount_pct"], row["max_uses_per_user"]


async def _redeem_promo(
    db: AsyncSession,
    *,
    promo_code_id: uuid.UUID,
    max_uses: int,
    user_id: uuid.UUID,
    booking_id: uuid.UUID,
    now: dt.datetime,
) -> None:
    """Atomic per-user counter + redemption row. Over-limit -> 422 (whole txn
    rolls back, so the booking insert is undone too)."""
    counted = (
        await db.execute(
            text(
                "INSERT INTO promo_usage_counters (promo_code_id, user_id, redemption_count) "
                "VALUES (:pid, :uid, 1) "
                "ON CONFLICT (promo_code_id, user_id) DO UPDATE "
                "SET redemption_count = promo_usage_counters.redemption_count + 1 "
                "WHERE promo_usage_counters.redemption_count < :max "
                "RETURNING redemption_count"
            ),
            {"pid": str(promo_code_id), "uid": str(user_id), "max": max_uses},
        )
    ).scalar_one_or_none()
    if counted is None or counted > max_uses:
        raise HTTPException(
            http.HTTP_422_UNPROCESSABLE_ENTITY, "Promo code usage limit reached."
        )
    await db.execute(
        text(
            "INSERT INTO promo_redemptions (id, promo_code_id, user_id, booking_id, redeemed_at) "
            "VALUES (:id, :pid, :uid, :bid, :now)"
        ),
        {
            "id": str(uuid.uuid4()),
            "pid": str(promo_code_id),
            "uid": str(user_id),
            "bid": str(booking_id),
            "now": now,
        },
    )


async def _lookup_duplicate_response(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    puja_id: uuid.UUID,
    slot_date: dt.date,
    slot_time: dt.time,
    now: dt.datetime,
) -> BookingCreateResponse | None:
    """Fetch the existing active booking for an idempotent duplicate submit."""
    existing = (
        await db.execute(
            select(Booking).where(
                Booking.user_id == user_id,
                Booking.puja_id == puja_id,
                Booking.scheduled_date == slot_date,
                Booking.scheduled_time == slot_time,
                Booking.cancelled_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        return None

    hold_expires_at = now + dt.timedelta(minutes=15)
    if existing.hold_id is not None:
        hold_expires = (
            await db.execute(
                select(SlotHold.expires_at).where(SlotHold.id == existing.hold_id)
            )
        ).scalar_one_or_none()
        if hold_expires is not None:
            hold_expires_at = hold_expires

    fee = Decimal(str(getattr(existing, "booking_fee", 0) or 0))
    razorpay_amount = fee if existing.payment_mode == _LAUNCH_MODE else Decimal(
        str(existing.amount_due_online)
    )

    return BookingCreateResponse(
        booking_id=existing.id,
        booking_class=existing.booking_class,  # type: ignore[arg-type]
        razorpay_order_id=existing.razorpay_order_id,
        amount_due_online=Decimal(str(existing.amount_due_online)),
        amount_due_offline=Decimal(str(existing.amount_due_offline)),
        total_amount=Decimal(str(existing.total_amount)),
        booking_fee=fee,
        booking_fee_label=BOOKING_FEE_LABEL if existing.payment_mode == _LAUNCH_MODE else None,
        razorpay_amount=razorpay_amount,
        payment_mode=existing.payment_mode,
        hold_expires_at=hold_expires_at,
        idempotent=True,
    )


async def create_booking(
    db: AsyncSession, *, user_id: uuid.UUID, payload: BookingCreate
) -> BookingCreateResponse:
    now = dt.datetime.now(dt.UTC)
    payment_mode = _assert_launch_payment_mode(payload.payment_mode)

    # (a) lock the hold
    hold = (
        await db.execute(
            select(SlotHold).where(SlotHold.id == payload.hold_id).with_for_update()
        )
    ).scalar_one_or_none()
    if hold is None or hold.user_id != user_id:
        raise HTTPException(http.HTTP_410_GONE, "Hold not found.")
    if hold.released_at is not None or hold.expires_at <= now:
        raise HTTPException(http.HTTP_410_GONE, "Hold expired.")

    slot_date = hold.slot_date
    slot_time = hold.slot_time
    puja_id = payload.puja_id
    hold_id = hold.id

    addr_geom = (
        await db.execute(
            text("SELECT geom IS NOT NULL FROM addresses WHERE id = :aid AND user_id = :uid"),
            {"aid": str(payload.address_id), "uid": str(user_id)},
        )
    ).scalar_one_or_none()
    if addr_geom is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "Address not found.")
    if addr_geom is False:
        raise HTTPException(http.HTTP_422_UNPROCESSABLE_ENTITY, "Address has no coordinates.")

    puja = (await db.execute(select(Puja).where(Puja.id == puja_id))).scalar_one_or_none()
    if puja is None or not puja.is_active:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "Puja not found.")

    addon_prices: list[Decimal] = []
    addon_rows: list[PujaAddon] = []
    if payload.addon_ids:
        addon_rows = list(
            (
                await db.execute(
                    select(PujaAddon).where(
                        PujaAddon.id.in_(payload.addon_ids),
                        PujaAddon.puja_id == puja_id,
                        PujaAddon.is_active.is_(True),
                    )
                )
            ).scalars()
        )
        if len(addon_rows) != len(set(payload.addon_ids)):
            raise HTTPException(http.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid add-on(s).")
        addon_prices = [Decimal(str(a.price)) for a in addon_rows]

    promo_pct = 0
    promo_code_id: uuid.UUID | None = None
    promo_max_uses = 0
    if payload.promo_code:
        promo_code_id, promo_pct, promo_max_uses = await _validate_promo(
            db, payload.promo_code, now
        )

    total, online, offline, booking_fee = await compute_amounts(
        db,
        puja_id=puja_id,
        pujari_id=None,
        addon_prices=addon_prices,
        promo_pct=promo_pct,
        payment_mode=payment_mode,
    )

    gate_settings = await load_booking_gate_settings(db)
    gate = assert_booking_gate(slot_date, slot_time, gate_settings, now=now)

    await assert_dispatch_supply(
        db,
        puja_id=puja_id,
        scheduled_date=slot_date,
        scheduled_time=slot_time,
        duration_minutes=puja.duration_minutes,
    )

    policy_id = (
        await db.execute(select(CancellationPolicy.id).order_by(CancellationPolicy.id).limit(1))
    ).scalar_one_or_none()
    if policy_id is None:
        raise RuntimeError("Seed data missing: cancellation_policies")

    pending_id = await status_id(db, "booking", "payment_pending")

    razorpay_charge = booking_fee if payment_mode == _LAUNCH_MODE else online

    booking_id = uuid.uuid4()
    insert_stmt = (
        pg_insert(Booking)
        .values(
            id=booking_id,
            user_id=user_id,
            pujari_id=None,
            puja_id=puja_id,
            address_id=payload.address_id,
            status_id=pending_id,
            cancellation_policy_id=policy_id,
            scheduled_date=slot_date,
            scheduled_time=slot_time,
            duration_minutes=puja.duration_minutes,
            cancelled_at=None,
            total_amount=total,
            intended_pujari_id=None,
            hold_id=hold_id,
            paid_at=None,
            dispatch_mode="broadcast",
            booking_class=gate.booking_class,
            payment_mode=payment_mode,
            amount_due_online=online,
            amount_due_offline=offline,
            booking_fee=booking_fee,
            razorpay_order_id=None,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_nothing(
            index_elements=["user_id", "puja_id", "scheduled_date", "scheduled_time"],
            index_where=text("cancelled_at IS NULL"),
        )
        .returning(Booking.id)
    )
    inserted_id = (await db.execute(insert_stmt)).scalar_one_or_none()

    if inserted_id is None:
        dup = await _lookup_duplicate_response(
            db,
            user_id=user_id,
            puja_id=puja_id,
            slot_date=slot_date,
            slot_time=slot_time,
            now=now,
        )
        if dup is None:
            raise RuntimeError(
                "ux_bookings_no_duplicate_submit blocked insert but no active row found"
            )
        log.info(
            "booking_duplicate_submit",
            existing_booking_id=str(dup.booking_id),
            user_id=str(user_id),
        )
        raise DuplicateBookingSubmit(dup)

    if promo_code_id is not None:
        await _redeem_promo(
            db,
            promo_code_id=promo_code_id,
            max_uses=promo_max_uses,
            user_id=user_id,
            booking_id=booking_id,
            now=now,
        )

    for a in addon_rows:
        db.add(
            BookingAddon(
                id=uuid.uuid4(),
                booking_id=booking_id,
                addon_id=a.id,
                price_at_booking=Decimal(str(a.price)),
            )
        )

    order_id = await razorpay_client.create_order(
        amount_paise=int((razorpay_charge * 100).quantize(Decimal("1"))),
        receipt=str(booking_id),
        notes={"booking_id": str(booking_id), "payment_mode": payment_mode},
    )
    await db.execute(
        update(Booking)
        .where(Booking.id == booking_id)
        .values(razorpay_order_id=order_id, updated_at=now)
    )

    hold.expires_at = now + dt.timedelta(minutes=15)
    await db.flush()

    log.info(
        "booking_created",
        booking_id=str(booking_id),
        payment_mode=payment_mode,
        booking_fee=str(booking_fee),
    )
    return BookingCreateResponse(
        booking_id=booking_id,
        booking_class=gate.booking_class,
        razorpay_order_id=order_id,
        amount_due_online=online,
        amount_due_offline=offline,
        total_amount=total,
        booking_fee=booking_fee,
        booking_fee_label=BOOKING_FEE_LABEL if payment_mode == _LAUNCH_MODE else None,
        razorpay_amount=razorpay_charge,
        payment_mode=payment_mode,
        hold_expires_at=hold.expires_at,
    )
