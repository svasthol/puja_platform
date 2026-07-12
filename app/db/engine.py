"""
Async database engine — psycopg3 + SQLAlchemy 2.0 AsyncEngine.

PgBouncer transaction-mode notes:
  - pool_pre_ping=True: SELECT 1 before reuse to detect stale connections.
  - pool_recycle: periodic reconnect so PgBouncer idle timeout doesn't strand conns.
  - No session-level SET across transactions; SET LOCAL inside a txn only.

Dependencies:
  - get_db:        a plain session (caller manages transactions).
  - get_db_txn:    a session already inside `session.begin()` — auto commit on
                   success, auto rollback on exception. Use this for write paths
                   so a constraint/trigger error rolls back cleanly and surfaces
                   to the shared exception handler.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

settings = get_settings()

engine: AsyncEngine = create_async_engine(
    str(settings.DATABASE_URL),
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=settings.DATABASE_POOL_RECYCLE,
    echo=settings.DEBUG,
)

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Plain session — read paths / caller-managed transactions."""
    async with AsyncSessionLocal() as session:
        yield session


async def get_db_txn() -> AsyncGenerator[AsyncSession, None]:
    """Transactional session — the whole request runs in one transaction.
    Commits on success, rolls back on any exception (so DB errors surface to
    the shared handler instead of leaving a half-applied write)."""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            yield session
