import os
import uuid

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("APP_ENV", "test")

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.db.base import Base
from app.db.session import engine
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


@pytest.fixture
def unique_email():
    return f"test-{uuid.uuid4().hex[:8]}@example.com"
