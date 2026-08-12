"""
Pytest fixtures for launch-gate tests.

Requires a live PostgreSQL 16 + PostGIS built from spec/db/*.sql and reachable
via DATABASE_URL. These are integration tests by design: the whole point of this
platform is that the DATABASE enforces the invariants, so tests that mock the DB
would prove nothing. Run:

    createdb Mana_Guruji
    psql -d Mana_Guruji -f spec/db/schema.sql -f spec/db/triggers.sql \
         -f spec/db/seed.sql -f spec/db/migration_002.sql -f spec/db/migration_003.sql \
         -f spec/db/migration_004.sql -f spec/db/migration_005.sql -f spec/db/migration_006.sql \
         -f spec/db/migration_009.sql -f spec/db/migration_010.sql -f spec/db/migration_011.sql \
         -f spec/db/migration_012.sql -f spec/db/migration_013.sql -f spec/db/migration_014.sql \
         -f spec/db/migration_015.sql -f spec/db/migration_016.sql -f spec/db/migration_017.sql \
         -f spec/db/migration_018.sql
    export DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:5433/Mana_Guruji
    pytest -q
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# Load project .env so pytest uses the same DATABASE_URL as local dev.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# psycopg async cannot run on Windows ProactorEventLoop (pytest-asyncio default).
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://postgres@127.0.0.1:5433/Mana_Guruji"
)


@pytest.fixture(scope="session")
def engine():
    eng = create_async_engine(DATABASE_URL, echo=False)
    yield eng


@pytest_asyncio.fixture
async def session(engine):
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s


@pytest_asyncio.fixture
async def seed(engine):
    """Idempotent baseline fixtures: 2 customers, 2 pujaris, 1 puja, 1 address, policy."""
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        async with s.begin():
            await s.execute(text("""
                INSERT INTO cancellation_policies (name, refund_pct_before_24h, refund_pct_after_24h)
                VALUES ('standard', 100, 50) ON CONFLICT (name) DO NOTHING;
            """))
            await s.execute(text("""
                INSERT INTO puja_categories (name) VALUES ('Test Cat') ON CONFLICT (name) DO NOTHING;
            """))
            await s.execute(text("""
                INSERT INTO pujas (id, category_id, name, default_price, duration_minutes, is_active)
                VALUES ('11111111-1111-1111-1111-111111111111',
                        (SELECT id FROM puja_categories WHERE name='Test Cat'),
                        'Test Puja', 2100.00, 90, true)
                ON CONFLICT (id) DO NOTHING;
            """))
            for u, ph in [
                ('aaaaaaaa-0000-0000-0000-000000000001', '+910000000001'),
                ('aaaaaaaa-0000-0000-0000-000000000002', '+910000000002'),
                ('bbbbbbbb-0000-0000-0000-000000000001', '+910000000011'),
                ('bbbbbbbb-0000-0000-0000-000000000002', '+910000000012'),
            ]:
                await s.execute(text(
                    "INSERT INTO users (id, full_name, phone) VALUES (:id,'T',:ph) "
                    "ON CONFLICT (id) DO NOTHING"), {"id": u, "ph": ph})
            for pj, u in [
                ('cccccccc-0000-0000-0000-000000000001', 'bbbbbbbb-0000-0000-0000-000000000001'),
                ('cccccccc-0000-0000-0000-000000000002', 'bbbbbbbb-0000-0000-0000-000000000002'),
            ]:
                await s.execute(text(
                    "INSERT INTO pujaris (id, user_id, verification_status) "
                    "VALUES (:pj,:u,'verified') ON CONFLICT (user_id) DO NOTHING"), {"pj": pj, "u": u})
            await s.execute(text("""
                INSERT INTO service_areas (city, zone_name, is_active)
                VALUES ('Hyderabad', 'Test Zone', true)
                ON CONFLICT (city, zone_name) DO NOTHING;
            """))
            await s.execute(text("""
                INSERT INTO addresses (id, user_id, line1, city, latitude, longitude,
                    service_area_id, geom)
                VALUES ('dddddddd-0000-0000-0000-000000000001',
                        'aaaaaaaa-0000-0000-0000-000000000001','L1','Hyd',17.4,78.4,
                        (SELECT id FROM service_areas WHERE city='Hyderabad' AND zone_name='Test Zone'),
                        ST_SetSRID(ST_MakePoint(78.4,17.4),4326)::geography)
                ON CONFLICT (id) DO NOTHING;
            """))
    return True


@pytest.fixture
def uniq():
    """Fresh, collision-free values per test so the suite is rerunnable without teardown."""
    import datetime as _dt
    import random as _r

    class U:
        def __init__(self):
            # a random future date keeps (pujari, slot_date, slot_time) unique across runs
            self.date = (_dt.date(2035, 1, 1) + _dt.timedelta(days=_r.randint(0, 3000))).isoformat()
            self.date2 = (_dt.date(2045, 1, 1) + _dt.timedelta(days=_r.randint(0, 3000))).isoformat()

        @staticmethod
        def id():
            return str(uuid.uuid4())

    return U()
