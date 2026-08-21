"""Async SQLAlchemy engine and session dependency.

Why it exists: FastAPI and future repositories need a shared PostgreSQL
session. Chat currently stays in-memory in `main.py` and does not use this.

Responsibility: create the async engine, session factory, `get_db`, and the
declarative `Base` that ORM models inherit from. Does not run migrations.

Communicates with: `core.config` (database URL), `models.user` (`Base`), and
`auth_router` via `get_db`. Search endpoints do not use this module.
"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from src.search_engine.core.config import settings


class Base(DeclarativeBase):
    """Shared SQLAlchemy declarative base for all tables."""


engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
)

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncIterator[AsyncSession]:
    """Yield one request-scoped async session and commit if the request succeeds."""
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
