#!/usr/bin/env python3
"""
TEST ONLY — idempotent DB fixtures for tests/e2e_ui/ manual QA.

Ensures seed users exist AND links pujari rows to the user owning each
partner phone. OTP login alone does NOT create a pujaris row — that is why
heartbeat returns 403 "Not a pujari account."

Usage (project root, venv active, DATABASE_URL in .env):
  python tests/e2e_ui/ensure_seed.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


PARTNER_PHONES = ("+917675834207", "+919603059878")
CUSTOMER_PHONES = ("+919848022334", "+919030370417")
PUJA_IDS = (
    "11111111-1111-1111-1111-111111111111",  # Test Puja (ensure_seed)
    "e4444444-4444-4444-4444-444444444444",  # Mahalakshmi (dev_booking_flow_e2e)
)


async def main() -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.config import get_settings

    engine = create_async_engine(str(get_settings().DATABASE_URL))
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
                INSERT INTO puja_categories (name) VALUES ('E2E Category') ON CONFLICT (name) DO NOTHING;
            """))
            await s.execute(text("""
                INSERT INTO pujas (id, category_id, name, default_price, duration_minutes, is_active)
                VALUES ('11111111-1111-1111-1111-111111111111',
                        (SELECT id FROM puja_categories WHERE name='Test Cat'),
                        'Test Puja', 2100.00, 90, true)
                ON CONFLICT (id) DO NOTHING;
            """))
            await s.execute(text("""
                INSERT INTO pujas (id, category_id, name, default_price, duration_minutes, is_active)
                VALUES ('e4444444-4444-4444-4444-444444444444',
                        (SELECT id FROM puja_categories WHERE name='E2E Category'),
                        'Mahalakshmi', 1900.00, 90, true)
                ON CONFLICT (id) DO NOTHING;
            """))
            await s.execute(text("""
                INSERT INTO service_areas (city, zone_name, is_active)
                VALUES ('Hyderabad', 'E2E Zone', true)
                ON CONFLICT (city, zone_name) DO NOTHING;
            """))
            sa_id = (
                await s.execute(
                    text(
                        "SELECT id FROM service_areas "
                        "WHERE city='Hyderabad' AND zone_name='E2E Zone'"
                    )
                )
            ).scalar_one()
            for u, ph in [
                ("aaaaaaaa-0000-0000-0000-000000000001", "+919848022334"),
                ("aaaaaaaa-0000-0000-0000-000000000002", "+919030370417"),
                ("bbbbbbbb-0000-0000-0000-000000000001", "+917675834207"),
                ("bbbbbbbb-0000-0000-0000-000000000002", "+919603059878"),
            ]:
                await s.execute(
                    text(
                        "INSERT INTO users (id, full_name, phone, is_active, created_at, updated_at) "
                        "VALUES (:id, 'E2E User', :ph, true, now(), now()) "
                        "ON CONFLICT (phone) DO NOTHING"
                    ),
                    {"id": u, "ph": ph},
                )

            # Link pujaris row to whoever owns each partner phone (handles OTP-created users too).
            for ph in PARTNER_PHONES:
                await s.execute(
                    text(
                        """
                        INSERT INTO pujaris (id, user_id, verification_status, created_at, updated_at)
                        SELECT gen_random_uuid(), u.id, 'verified', now(), now()
                        FROM users u WHERE u.phone = :ph
                        ON CONFLICT (user_id) DO UPDATE
                        SET verification_status = 'verified', updated_at = now()
                        """
                    ),
                    {"ph": ph},
                )
                pj_id = (
                    await s.execute(
                        text(
                            "SELECT p.id FROM pujaris p JOIN users u ON u.id = p.user_id "
                            "WHERE u.phone = :ph"
                        ),
                        {"ph": ph},
                    )
                ).scalar_one()
                await s.execute(
                    text(
                        """
                        INSERT INTO pujari_service_areas (pujari_id, service_area_id)
                        VALUES (:pj, :sid) ON CONFLICT DO NOTHING
                        """
                    ),
                    {"pj": str(pj_id), "sid": sa_id},
                )
                for puja_id in PUJA_IDS:
                    price = 1900.00 if puja_id.startswith("e444") else 2100.00
                    await s.execute(
                        text(
                            """
                            INSERT INTO pujari_pricing (id, pujari_id, puja_id, base_price)
                            VALUES (gen_random_uuid(), :pj, :puja, :price)
                            ON CONFLICT (pujari_id, puja_id) DO NOTHING
                            """
                        ),
                        {"pj": str(pj_id), "puja": puja_id, "price": price},
                    )
                # E2E: price every active catalog puja so Load pujas → any puja can dispatch.
                await s.execute(
                    text(
                        """
                        INSERT INTO pujari_pricing (id, pujari_id, puja_id, base_price)
                        SELECT gen_random_uuid(), :pj, p.id, COALESCE(p.default_price, 2100)
                        FROM pujas p
                        WHERE p.is_active = true
                        ON CONFLICT (pujari_id, puja_id) DO NOTHING
                        """
                    ),
                    {"pj": str(pj_id)},
                )
                for dow, st, et in [(0, "06:00", "23:59"), (1, "06:00", "23:59"), (2, "06:00", "23:59"),
                                    (3, "06:00", "23:59"), (4, "06:00", "23:59"), (5, "06:00", "23:59"),
                                    (6, "06:00", "23:59")]:
                    await s.execute(
                        text(
                            """
                            INSERT INTO pujari_availability (id, pujari_id, day_of_week, start_time, end_time)
                            SELECT gen_random_uuid(), :pj, :dow, :st, :et
                            WHERE NOT EXISTS (
                                SELECT 1 FROM pujari_availability
                                WHERE pujari_id = :pj AND day_of_week = :dow
                            )
                            """
                        ),
                        {"pj": str(pj_id), "dow": dow, "st": st, "et": et},
                    )
                await s.execute(
                    text(
                        """
                        UPDATE pujari_availability
                        SET start_time = '06:00', end_time = '23:59'
                        WHERE pujari_id = :pj
                        """
                    ),
                    {"pj": str(pj_id)},
                )
                await s.execute(
                    text(
                        """
                        INSERT INTO pujari_live_location (pujari_id, latitude, longitude, geom, updated_at)
                        VALUES (:pj, 17.385044, 78.486671,
                                ST_SetSRID(ST_MakePoint(78.486671, 17.385044), 4326)::geography, now())
                        ON CONFLICT (pujari_id) DO UPDATE SET
                            latitude = EXCLUDED.latitude, longitude = EXCLUDED.longitude,
                            geom = EXCLUDED.geom, updated_at = now()
                        """
                    ),
                    {"pj": str(pj_id)},
                )

            await s.execute(
                text(
                    """
                    INSERT INTO addresses (
                        id, user_id, line1, city, latitude, longitude, service_area_id, geom
                    )
                    VALUES (
                        'dddddddd-0000-0000-0000-000000000001',
                        (SELECT id FROM users WHERE phone = '+919848022334'),
                        'L1', 'Hyderabad', 17.385044, 78.486671, :sa_id,
                        ST_SetSRID(ST_MakePoint(78.486671, 17.385044), 4326)::geography
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        service_area_id = EXCLUDED.service_area_id,
                        line1 = EXCLUDED.line1,
                        city = EXCLUDED.city,
                        latitude = EXCLUDED.latitude,
                        longitude = EXCLUDED.longitude,
                        geom = EXCLUDED.geom
                    """
                ),
                {"sa_id": sa_id},
            )

    await engine.dispose()
    print("E2E seed OK.")
    print("Partner phones (must use one of these):", ", ".join(PARTNER_PHONES))
    print("Customer phones:", ", ".join(CUSTOMER_PHONES))
    print("Recommended puja for offers E2E:", PUJA_IDS[0], "(Test Puja)")
    print("Re-login on Partner tab after running this if you already OTP'd with another phone.")
    print("Pujari pricing seeded for ALL active pujas + fixed IDs:", ", ".join(PUJA_IDS))


if __name__ == "__main__":
    asyncio.run(main())
