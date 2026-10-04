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


async def test_admin_tenants_requires_auth(client):
    assert (await client.get("/api/v1/admin/tenants")).status_code == 401


async def test_platform_admin_sees_cross_tenant_list(client, unique_email):
    # Dev bootstrap always creates a platform_admin, so this user can see
    # the full cross-tenant list — intentionally not tenant-scoped.
    headers_a = await _auth_headers(client, unique_email)
    await _auth_headers(client, f"b-{unique_email}")  # a second, distinct tenant

    res = await client.get("/api/v1/admin/tenants", headers=headers_a)
    assert res.status_code == 200
    body = res.json()
    assert len(body) >= 2
    for tenant in body:
        assert "user_count" in tenant
        assert "plan_slug" in tenant


async def test_non_admin_cannot_view_admin_tenants(client, unique_email):
    headers = await _auth_headers(client, unique_email)
    async with async_session_factory() as db:
        result = await db.execute(select(User).where(User.email == unique_email))
        user = result.scalar_one()
        user.role = Role.VIEWER
        db.add(user)
        await db.commit()

    res = await client.get("/api/v1/admin/tenants", headers=headers)
    assert res.status_code == 403
