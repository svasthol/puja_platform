"""
Alembic migrations environment — async psycopg3 + SQLAlchemy 2.0.

CRITICAL: The first three migrations are raw SQL files executed verbatim.
Never let autogenerate produce migrations 001, 002, or 003.
See spec/DATABASE.md "Alembic integration" section.
"""
import asyncio
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings

settings = get_settings()
config = context.config
config.set_main_option("sqlalchemy.url", str(settings.DATABASE_URL))

if config.config_file_name:
    fileConfig(config.config_file_name)

# Import all models so Alembic sees the metadata
from app.db.base import Base  # noqa: F401, E402
import app.models  # noqa: F401, E402  — imports all models

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = create_async_engine(
        str(settings.DATABASE_URL),
        poolclass=pool.NullPool,           # Alembic gets a single connection, not a pool
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # Review autogenerate output carefully for excluded objects (see DATABASE.md):
        #   - exclusion constraints (ex_bookings_*)
        #   - partial unique indexes (ux_slot_holds_active, ux_bookings_*)
        #   - triggers and trigger functions
        #   - PostGIS geography columns / gist indexes
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    # psycopg async on Windows requires SelectorEventLoop, not ProactorEventLoop.
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_migrations_online())
