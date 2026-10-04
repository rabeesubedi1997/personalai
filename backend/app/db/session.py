"""Async SQLAlchemy engine/session factory, provider-agnostic (sqlite for
Phase-1 zero-install dev, postgresql+asyncpg for the spec's intended target —
switching is a DATABASE_URL change, nothing else)."""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_async_engine(
    settings.database_url,
    echo=False,
    connect_args=connect_args,
)

async_session_factory = async_sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session
