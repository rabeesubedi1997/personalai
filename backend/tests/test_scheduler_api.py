import pytest
from sqlalchemy import select

from app.db.session import async_session_factory
from app.models.user import Role, User

pytestmark = pytest.mark.asyncio


async def _auth_headers(client, email: str) -> dict:
    await client.post("/api/v1/auth/bootstrap", json={"email": email, "password": "pw123456"})
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "pw123456"})
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_scheduler_run_requires_auth(client):
    assert (await client.post("/api/v1/scheduler/run")).status_code == 401


async def test_platform_admin_can_trigger_scheduler(client, unique_email):
    # Dev bootstrap always creates a platform_admin user.
    headers = await _auth_headers(client, unique_email)
    res = await client.post("/api/v1/scheduler/run", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert "failed_agent_run_follow_up" in body
    assert "stale_pending_approval_reminder" in body
    assert "stale_request_escalation" in body


async def test_non_admin_cannot_trigger_scheduler(client, unique_email):
    headers = await _auth_headers(client, unique_email)

    # Downgrade the bootstrapped user's role directly — simulates a
    # non-admin user without needing a role-assignment endpoint (not built
    # yet; RBAC beyond the Role enum is Phase 6+/deferred).
    async with async_session_factory() as db:
        result = await db.execute(select(User).where(User.email == unique_email))
        user = result.scalar_one()
        user.role = Role.VIEWER
        db.add(user)
        await db.commit()

    res = await client.post("/api/v1/scheduler/run", headers=headers)
    assert res.status_code == 403
