import os
import uuid

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("APP_ENV", "test")
# The ASGI test client doesn't trigger app lifespan anyway, but keep this
# explicit rather than relying on that incidentally (see app/main.py).
os.environ.setdefault("SCHEDULER_ENABLED", "false")
os.environ.setdefault("CACHE_WARMER_ENABLED", "false")

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.db.base import Base
from app.db.session import async_session_factory, engine
from app.main import app


@pytest_asyncio.fixture
async def client():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session():
    """Raw async DB session for tests that exercise a service layer
    directly (e.g. MemoryStore) without going through the HTTP API."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session_factory() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def unique_email():
    return f"test-{uuid.uuid4().hex[:8]}@example.com"
