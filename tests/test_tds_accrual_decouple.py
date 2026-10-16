"""§0.S — TDS accrual decouple (migration 027)."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.services import tds_accrual_service

pytestmark = pytest.mark.booking_fee_launch

PUJARI_ID = uuid.UUID("cccccccc-0000-0000-0000-000000000001")
CUSTOMER_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
ADDRESS_ID = uuid.UUID("dddddddd-0000-0000-0000-000000000001")
PUJA_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


async def _require_migration_027(session) -> None:
    row = (
        await session.execute(
            text(
                """
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = 'pujari_tds_accrual_intents'
                """
            )
        )
    ).scalar_one_or_none()
    if row is None:
        pytest.skip("migration_027 not applied — run: python scripts/apply_migration_027.py")


async def _set_pujari(session, *, entity_type: str | None = "individual", pan: bool = True) -> None:
    pan_hash = ("a" * 64) if pan else None
    pan_status = "operative" if pan else "unverified"
    await session.execute(
        text(
            """
            UPDATE pujaris
            SET entity_type = :et, pan_hash = :ph, pan_status = :ps
            WHERE id = :pid
            """
        ),
        {"et": entity_type, "ph": pan_hash, "ps": pan_status, "pid": str(PUJARI_ID)},
    )


async def _insert_booking(
    session,
    booking_id: uuid.UUID,
    *,
    snap_entity_type: str | None = "individual",
    snap_pan_on_file: bool = True,
    total_amount: Decimal = Decimal("2100"),
    record_balance_at_insert: bool = False,
) -> None:
    h = int(booking_id.hex[:12], 16)
    h2 = int(booking_id.hex[12:24], 16)
    h3 = int(booking_id.hex[24:36], 16)
    slot_time = f"{(h % 10) + 8:02d}:{(h2 % 60):02d}:{(h3 % 60):02d}"
    day_offset = 500 + (h % 4000) + (h2 % 4000)
    if not record_balance_at_insert:
        snap_entity_type = None
        snap_pan_on_file = None
    balance_sql = (
        "now(), (SELECT user_id FROM pujaris WHERE id = :pid), 'cash', :total"
        if record_balance_at_insert
        else "NULL, NULL, NULL, NULL"
    )
    await session.execute(
        text(
            f"""
            INSERT INTO bookings (
                id, user_id, pujari_id, intended_pujari_id, puja_id, address_id, status_id,
                cancellation_policy_id, scheduled_date, scheduled_time, duration_minutes,
                total_amount, amount_due_online, amount_due_offline, booking_fee,
                payment_mode, paid_at, dispatch_mode, balance_collected_at,
                balance_collected_by, balance_collection_method, balance_collected_amount,
                tds_snapshot_entity_type, tds_snapshot_pan_on_file,
                created_at, updated_at
            )
            SELECT
                :bid, :uid, :pid, :pid, :puja, :addr, st.id,
                (SELECT id FROM cancellation_policies WHERE name='standard'),
                current_date + :day_off, CAST(:slot AS time), 90, :total, 0, :total, 61,
                'booking_fee', now(), 'broadcast', {balance_sql},
                :snap_et, :snap_pan, now(), now()
            FROM status_types st
            WHERE st.domain = 'booking' AND st.code = 'confirmed'
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {
            "bid": str(booking_id),
            "uid": str(CUSTOMER_ID),
            "pid": str(PUJARI_ID),
            "puja": str(PUJA_ID),
            "addr": str(ADDRESS_ID),
            "day_off": day_offset,
            "slot": slot_time,
            "snap_et": snap_entity_type,
            "snap_pan": snap_pan_on_file,
            "total": str(total_amount),
        },
    )


@pytest.mark.asyncio
async def test_enqueue_parks_without_entity_type(engine, seed, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "TDS_ACCRUAL_ENABLED", True)
    maker = __import__(
        "sqlalchemy.ext.asyncio", fromlist=["async_sessionmaker"]
    ).async_sessionmaker(engine, expire_on_commit=False)
    booking_id = uuid.uuid4()
    async with maker() as session:
        async with session.begin():
            await _require_migration_027(session)
            await _set_pujari(session, entity_type=None, pan=False)
            await _insert_booking(
                session, booking_id, snap_entity_type=None, snap_pan_on_file=False
            )
            result = await tds_accrual_service.enqueue_tds_accrual_intent(
                session,
                booking_id=booking_id,
                pujari_id=PUJARI_ID,
                gross_amount=Decimal("2100"),
            )
            assert result["skipped"] is True
            assert "parked" in (result.get("message") or "").lower()
            status = (
                await session.execute(
                    text(
                        "SELECT status FROM pujari_tds_accrual_intents WHERE booking_id = :bid"
                    ),
                    {"bid": str(booking_id)},
                )
            ).scalar_one()
            assert status == "parked"


async def _cancel_foreign_accrual_intents(session, *, keep_booking_ids: set[uuid.UUID]) -> None:
    ids = [str(b) for b in keep_booking_ids]
    if not ids:
        return
    await session.execute(
        text(
            """
            UPDATE pujari_tds_accrual_intents
            SET status = 'cancelled'
            WHERE status IN ('pending', 'parked')
              AND NOT (booking_id = ANY(CAST(:keep AS uuid[])))
            """
        ),
        {"keep": ids},
    )


@pytest.mark.asyncio
async def test_worker_processes_intent_in_order(engine, seed, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "TDS_ACCRUAL_ENABLED", True)
    maker = __import__(
        "sqlalchemy.ext.asyncio", fromlist=["async_sessionmaker"]
    ).async_sessionmaker(engine, expire_on_commit=False)
    bid1, bid2 = uuid.uuid4(), uuid.uuid4()
    async with maker() as session:
        async with session.begin():
            await _require_migration_027(session)
            await _set_pujari(session)
            await _seed_fy(session, Decimal("490000"))
            await _insert_booking(session, bid1)
            await _insert_booking(session, bid2)
            await _require_migration_v3(session)
            await _apply_tds_at_accept(session, bid1, monkeypatch=monkeypatch)
            await _apply_tds_at_accept(session, bid2, monkeypatch=monkeypatch)
            await tds_accrual_service.enqueue_tds_accrual_intent(
                session, booking_id=bid1, pujari_id=PUJARI_ID, gross_amount=Decimal("2100")
            )
            await tds_accrual_service.enqueue_tds_accrual_intent(
                session, booking_id=bid2, pujari_id=PUJARI_ID, gross_amount=Decimal("20000")
            )
            await _cancel_foreign_accrual_intents(session, keep_booking_ids={bid1, bid2})

    async with maker() as session:
        async with session.begin():
            counts = await tds_accrual_service.process_pending_accrual_intents(session)
            assert counts["processed"] == 2
            ledger = (
                await session.execute(
                    text(
                        """
                        SELECT count(*) FROM pujari_tds_facilitation_ledger
                        WHERE booking_id IN (:b1, :b2) AND entry_type = 'accrual'
                        """
                    ),
                    {"b1": str(bid1), "b2": str(bid2)},
                )
            ).scalar_one()
            assert ledger == 2


@pytest.mark.asyncio
async def test_reversal_unconditional_when_flag_off(engine, seed, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "TDS_ACCRUAL_ENABLED", True)
    maker = __import__(
        "sqlalchemy.ext.asyncio", fromlist=["async_sessionmaker"]
    ).async_sessionmaker(engine, expire_on_commit=False)
    booking_id = uuid.uuid4()
    async with maker() as session:
        async with session.begin():
            await _require_migration_027(session)
            await _set_pujari(session)
            await _seed_fy(session, Decimal("510000"))
            await _insert_booking(session, booking_id, total_amount=Decimal("3000"))
            await _require_migration_v3(session)
            await _apply_tds_at_accept(session, booking_id, monkeypatch=monkeypatch)
            await tds_accrual_service.accrue_tds_on_balance_collected(
                session,
                booking_id=booking_id,
                pujari_id=PUJARI_ID,
                gross_amount=Decimal("3000"),
            )

    monkeypatch.setattr(settings, "TDS_ACCRUAL_ENABLED", False)
    async with maker() as session:
        async with session.begin():
            rev = await tds_accrual_service.reverse_tds_on_cancel(
                session, booking_id=booking_id, pujari_id=PUJARI_ID
            )
            assert rev["reversed"] is True


async def _seed_fy(session, gross: Decimal) -> None:
    fy_start = tds_accrual_service.fy_start_for_date(
        __import__("datetime").date.today()
    )
    await session.execute(
        text(
            """
            INSERT INTO pujari_tax_year (pujari_id, fy_start, gross_facilitation, tds_accrued)
            VALUES (:pid, :fy, :gross, 0)
            ON CONFLICT (pujari_id, fy_start) DO UPDATE
            SET gross_facilitation = :gross,
                tds_accrued = 0,
                deduction_latched = false,
                updated_at = now()
            """
        ),
        {"pid": str(PUJARI_ID), "fy": fy_start, "gross": str(gross)},
    )


async def _apply_tds_at_accept(session, booking_id: uuid.UUID, *, monkeypatch) -> None:
    from app.core.config import get_settings
    from app.services.tds_v3_accept_service import apply_tds_at_booking_confirmation

    monkeypatch.setattr(get_settings(), "TDS_ACCEPT_STUB_COLLECT", True)
    await apply_tds_at_booking_confirmation(
        session, booking_id=booking_id, pujari_id=PUJARI_ID
    )


@pytest.mark.asyncio
async def test_worker_poison_intent_quarantined_later_intent_accrues(
    engine, seed, monkeypatch
):
    """D6 reversion — SAVEPOINT quarantine; failed row persists; batch continues."""
    from app.core.config import get_settings
    from sqlalchemy.exc import IntegrityError

    monkeypatch.setattr(get_settings(), "TDS_ACCRUAL_ENABLED", True)
    maker = __import__(
        "sqlalchemy.ext.asyncio", fromlist=["async_sessionmaker"]
    ).async_sessionmaker(engine, expire_on_commit=False)
    poison_bid, ok_bid = uuid.uuid4(), uuid.uuid4()
    real_execute = tds_accrual_service._execute_accrual

    async def flaky_execute(db, **kwargs):
        if kwargs["booking_id"] == poison_bid:
            raise IntegrityError("INSERT", {}, Exception("duplicate accrual"))
        return await real_execute(db, **kwargs)

    monkeypatch.setattr(tds_accrual_service, "_execute_accrual", flaky_execute)

    async with maker() as session:
        async with session.begin():
            await _require_migration_027(session)
            await _set_pujari(session)
            await _insert_booking(session, poison_bid)
            await _insert_booking(session, ok_bid)
            await _require_migration_v3(session)
            await _apply_tds_at_accept(session, poison_bid, monkeypatch=monkeypatch)
            await _apply_tds_at_accept(session, ok_bid, monkeypatch=monkeypatch)
            await tds_accrual_service.enqueue_tds_accrual_intent(
                session,
                booking_id=poison_bid,
                pujari_id=PUJARI_ID,
                gross_amount=Decimal("2100"),
            )
            await tds_accrual_service.enqueue_tds_accrual_intent(
                session,
                booking_id=ok_bid,
                pujari_id=PUJARI_ID,
                gross_amount=Decimal("2100"),
            )
            await session.execute(
                text(
                    """
                    UPDATE pujari_tds_accrual_intents
                    SET collected_at = now() - interval '2 days'
                    WHERE booking_id = :bid
                    """
                ),
                {"bid": str(poison_bid)},
            )
            await _cancel_foreign_accrual_intents(
                session, keep_booking_ids={poison_bid, ok_bid}
            )

    async with maker() as session:
        async with session.begin():
            counts = await tds_accrual_service.process_pending_accrual_intents(session)
            assert counts["failed"] == 1
            assert counts["processed"] == 1

    async with maker() as verify:
        poison = (
            await verify.execute(
                text(
                    """
                    SELECT status, attempt_count, last_error
                    FROM pujari_tds_accrual_intents
                    WHERE booking_id = :bid
                    """
                ),
                {"bid": str(poison_bid)},
            )
        ).one()
        assert poison.status == "failed"
        assert poison.attempt_count >= 1
        assert poison.last_error
        ok_ledger = (
            await verify.execute(
                text(
                    """
                    SELECT count(*) FROM pujari_tds_facilitation_ledger
                    WHERE booking_id = :bid AND entry_type = 'accrual'
                    """
                ),
                {"bid": str(ok_bid)},
            )
        ).scalar_one()
        assert ok_ledger == 1


@pytest.mark.asyncio
async def test_accrual_uses_statutory_row_as_of_collected_at(engine, seed, monkeypatch):
    """R15 reversion — future effective_from row must not change past collections."""
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "TDS_ACCRUAL_ENABLED", True)
    maker = __import__(
        "sqlalchemy.ext.asyncio", fromlist=["async_sessionmaker"]
    ).async_sessionmaker(engine, expire_on_commit=False)
    booking_id = uuid.uuid4()
    async with maker() as session:
        async with session.begin():
            await _require_migration_027(session)
            await _insert_future_statutory_row(session)
            await _set_pujari(session, entity_type="company", pan=True)
            await _insert_booking(
                session, booking_id, snap_entity_type="company", snap_pan_on_file=True
            )
            await _require_migration_v3(session)
            await _apply_tds_at_accept(session, booking_id, monkeypatch=monkeypatch)
            await tds_accrual_service.enqueue_tds_accrual_intent(
                session,
                booking_id=booking_id,
                pujari_id=PUJARI_ID,
                gross_amount=Decimal("2100"),
            )
            await _cancel_foreign_accrual_intents(session, keep_booking_ids={booking_id})

    async with maker() as session:
        async with session.begin():
            counts = await tds_accrual_service.process_pending_accrual_intents(session)
            assert counts["processed"] == 1
            tds_amount = (
                await session.execute(
                    text(
                        """
                        SELECT tds_amount FROM pujari_tds_facilitation_ledger
                        WHERE booking_id = :bid AND entry_type = 'accrual'
                        """
                    ),
                    {"bid": str(booking_id)},
                )
            ).scalar_one()
            assert tds_amount == Decimal("2.10")


async def _insert_future_statutory_row(session) -> None:
    has_statutory = (
        await session.execute(text("SELECT 1 FROM tax_statutory_config LIMIT 1"))
    ).scalar_one_or_none()
    if has_statutory is None:
        pytest.skip("tax_statutory_config empty")
    await session.execute(
        text(
            """
            INSERT INTO tax_statutory_config (
                effective_from,
                advisor_signoff_ref,
                tds_no_pan_rate_pct,
                tds_pan_entity_rate_pct,
                tds_individual_fy_threshold_inr,
                tds_fy_turnover_warn_inr,
                tds_fy_turnover_block_inr,
                tds_always_taxed_entity_types
            )
            VALUES (
                current_date + 400,
                'R15-TEST-FUTURE',
                5,
                50,
                500000,
                1800000,
                2000000,
                '["firm","trust","company","aop","other"]'::jsonb
            )
            ON CONFLICT (effective_from) DO UPDATE
            SET tds_pan_entity_rate_pct = EXCLUDED.tds_pan_entity_rate_pct
            """
        )
    )


@pytest.mark.asyncio
async def test_catch_up_accrual_statutory_as_of_collected_at(engine, seed, monkeypatch):
    """R15 — catch_up path (`accrue_tds_on_balance_collected`) same as-of rule as worker."""
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "TDS_ACCRUAL_ENABLED", True)
    maker = __import__(
        "sqlalchemy.ext.asyncio", fromlist=["async_sessionmaker"]
    ).async_sessionmaker(engine, expire_on_commit=False)
    booking_id = uuid.uuid4()
    collected_at = __import__("datetime").datetime.now(__import__("datetime").UTC)
    async with maker() as session:
        async with session.begin():
            await _require_migration_027(session)
            await _insert_future_statutory_row(session)
            await _set_pujari(session, entity_type="company", pan=True)
            await _insert_booking(
                session, booking_id, snap_entity_type="company", snap_pan_on_file=True
            )
            await _require_migration_v3(session)
            await _apply_tds_at_accept(session, booking_id, monkeypatch=monkeypatch)

    async with maker() as session:
        async with session.begin():
            await tds_accrual_service.accrue_tds_on_balance_collected(
                session,
                booking_id=booking_id,
                pujari_id=PUJARI_ID,
                gross_amount=Decimal("2100"),
                collected_at=collected_at,
            )

    async with maker() as verify:
        tds_amount = (
            await verify.execute(
                text(
                    """
                    SELECT tds_amount FROM pujari_tds_facilitation_ledger
                    WHERE booking_id = :bid AND entry_type = 'accrual'
                    """
                ),
                {"bid": str(booking_id)},
            )
        ).scalar_one()
        assert tds_amount == Decimal("2.10")


def test_fy_read_and_lock_sql_split():
    """R3 reversion — read path must not embed FOR UPDATE (regression guard)."""
    import inspect

    read_src = inspect.getsource(tds_accrual_service._read_fy_row).upper()
    lock_src = inspect.getsource(tds_accrual_service._lock_fy_row).upper()
    assert "FOR UPDATE" not in read_src
    assert "FOR UPDATE" in lock_src


@pytest.mark.asyncio
async def test_fy_read_paths_do_not_lock_tax_year(engine, seed, monkeypatch):
    """R3 — preview/idempotent TDS responses must not lock FY hot row."""
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "TDS_ACCRUAL_ENABLED", True)
    maker = __import__(
        "sqlalchemy.ext.asyncio", fromlist=["async_sessionmaker"]
    ).async_sessionmaker(engine, expire_on_commit=False)
    real_read = tds_accrual_service._read_fy_row
    real_lock = tds_accrual_service._lock_fy_row
    read_calls = 0
    lock_calls = 0

    async def spy_read(db, **kwargs):
        nonlocal read_calls
        read_calls += 1
        return await real_read(db, **kwargs)

    async def spy_lock(db, **kwargs):
        nonlocal lock_calls
        lock_calls += 1
        return await real_lock(db, **kwargs)

    monkeypatch.setattr(tds_accrual_service, "_read_fy_row", spy_read)
    monkeypatch.setattr(tds_accrual_service, "_lock_fy_row", spy_lock)

    booking_id = uuid.uuid4()
    async with maker() as session:
        async with session.begin():
            await _require_migration_027(session)
            await _set_pujari(session)
            await _insert_booking(session, booking_id)
            await _require_migration_v3(session)
            await _apply_tds_at_accept(session, booking_id, monkeypatch=monkeypatch)
            await tds_accrual_service.accrue_tds_on_balance_collected(
                session,
                booking_id=booking_id,
                pujari_id=PUJARI_ID,
                gross_amount=Decimal("2100"),
            )

    read_calls = lock_calls = 0
    async with maker() as session:
        async with session.begin():
            await tds_accrual_service.tds_snapshot_for_booking(
                session, booking_id=booking_id, pujari_id=PUJARI_ID
            )
    assert read_calls >= 1
    assert lock_calls == 0


async def _require_migration_v3(session) -> None:
    row = (
        await session.execute(
            text(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'bookings'
                  AND column_name = 'tds_facilitation_fy_applied_at'
                """
            )
        )
    ).scalar_one_or_none()
    if row is None:
        pytest.skip("migration_029 v3 columns not applied")


@pytest.mark.asyncio
async def test_v3_accrual_sets_booking_snapshot_and_ledger_taxable_base(engine, seed, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "TDS_ACCRUAL_ENABLED", True)
    maker = __import__(
        "sqlalchemy.ext.asyncio", fromlist=["async_sessionmaker"]
    ).async_sessionmaker(engine, expire_on_commit=False)
    booking_id = uuid.uuid4()
    async with maker() as session:
        async with session.begin():
            await _require_migration_027(session)
            await _require_migration_v3(session)
            await _seed_fy(session, Decimal("490000"))
            await _set_pujari(session)
            await _insert_booking(session, booking_id, total_amount=Decimal("20000"))
            await _require_migration_v3(session)
            await _apply_tds_at_accept(session, booking_id, monkeypatch=monkeypatch)
            await tds_accrual_service.accrue_tds_on_balance_collected(
                session,
                booking_id=booking_id,
                pujari_id=PUJARI_ID,
                gross_amount=Decimal("20000"),
            )

    async with maker() as verify:
        snap = (
            await verify.execute(
                text(
                    """
                    SELECT b.tds_taxable_base, b.tds_collected_online, b.tds_facilitation_fy_applied_at,
                           y.deduction_latched
                    FROM bookings b
                    JOIN pujari_tax_year y ON y.pujari_id = b.pujari_id
                    WHERE b.id = :bid
                    """
                ),
                {"bid": str(booking_id)},
            )
        ).mappings().first()
        assert Decimal(str(snap["tds_taxable_base"])) == Decimal("10000.00")
        assert Decimal(str(snap["tds_collected_online"])) == Decimal("10.00")
        assert snap["tds_facilitation_fy_applied_at"] is not None
        assert snap["deduction_latched"] is True


@pytest.mark.asyncio
async def test_v3_ledger_only_when_fy_already_applied_no_double_turnover(engine, seed, monkeypatch):
    """Post-T6 shape: FY already incremented; balance accrual adds ledger + tds_accrued only."""
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "TDS_ACCRUAL_ENABLED", True)
    maker = __import__(
        "sqlalchemy.ext.asyncio", fromlist=["async_sessionmaker"]
    ).async_sessionmaker(engine, expire_on_commit=False)
    booking_id = uuid.uuid4()
    fy_start = tds_accrual_service.fy_start_for_date(__import__("datetime").date.today())
    async with maker() as session:
        async with session.begin():
            await _require_migration_027(session)
            await _require_migration_v3(session)
            await _set_pujari(session)
            await _insert_booking(session, booking_id, total_amount=Decimal("20000"))
            await session.execute(
                text(
                    """
                    INSERT INTO pujari_tax_year (
                        pujari_id, fy_start, gross_facilitation, tds_accrued, deduction_latched
                    ) VALUES (:pid, :fy, 510000, 10, true)
                    ON CONFLICT (pujari_id, fy_start) DO UPDATE
                    SET gross_facilitation = 510000, tds_accrued = 10, deduction_latched = true
                    """
                ),
                {"pid": str(PUJARI_ID), "fy": fy_start},
            )
            await session.execute(
                text(
                    """
                    UPDATE bookings
                    SET tds_collected_online = 10,
                        tds_liability_inr = 10,
                        tds_rate_applied = 0.001,
                        tds_taxable_base = 10000,
                        amount_due_offline = 19990,
                        tds_facilitation_fy_applied_at = now()
                    WHERE id = :bid
                    """
                ),
                {"bid": str(booking_id)},
            )

    async with maker() as session:
        async with session.begin():
            await tds_accrual_service.accrue_tds_on_balance_collected(
                session,
                booking_id=booking_id,
                pujari_id=PUJARI_ID,
                gross_amount=Decimal("20000"),
            )

    async with maker() as verify:
        fy = (
            await verify.execute(
                text(
                    """
                    SELECT gross_facilitation, tds_accrued, deduction_latched
                    FROM pujari_tax_year WHERE pujari_id = :pid AND fy_start = :fy
                    """
                ),
                {"pid": str(PUJARI_ID), "fy": fy_start},
            )
        ).mappings().first()
        assert Decimal(str(fy["gross_facilitation"])) == Decimal("510000")
        assert Decimal(str(fy["tds_accrued"])) == Decimal("10.00")
        assert fy["deduction_latched"] is True
        ledger_count = (
            await verify.execute(
                text(
                    """
                    SELECT count(*) FROM pujari_tds_facilitation_ledger
                    WHERE booking_id = :bid AND entry_type = 'accrual'
                    """
                ),
                {"bid": str(booking_id)},
            )
        ).scalar_one()
        assert ledger_count == 1
