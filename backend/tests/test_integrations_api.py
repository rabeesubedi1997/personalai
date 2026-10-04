import pytest

pytestmark = pytest.mark.asyncio


async def _auth_headers(client, email: str) -> dict:
    await client.post("/api/v1/auth/bootstrap", json={"email": email, "password": "pw123456"})
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "pw123456"})
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_integrations_require_auth(client):
    assert (await client.get("/api/v1/integrations/api-keys")).status_code == 401


async def test_create_list_and_revoke_api_key(client, unique_email):
    headers = await _auth_headers(client, unique_email)

    create_res = await client.post(
        "/api/v1/integrations/api-keys",
        json={"agent_slug": "general_assistant", "label": "My website widget"},
        headers=headers,
    )
    assert create_res.status_code == 201
    body = create_res.json()
    assert body["api_key"].startswith("pak_")
    assert body["agent_slug"] == "general_assistant"
    key_id = body["id"]

    list_res = await client.get("/api/v1/integrations/api-keys", headers=headers)
    assert list_res.status_code == 200
    listed = list_res.json()
    assert len(listed) == 1
    # The raw key must never be returned again after creation.
    assert "api_key" not in listed[0]
    assert listed[0]["key_prefix"] == body["key_prefix"]

    revoke_res = await client.delete(f"/api/v1/integrations/api-keys/{key_id}", headers=headers)
    assert revoke_res.status_code == 200
    assert revoke_res.json()["is_active"] is False


async def test_cannot_create_key_for_unknown_agent(client, unique_email):
    headers = await _auth_headers(client, unique_email)
    res = await client.post(
        "/api/v1/integrations/api-keys",
        json={"agent_slug": "not_a_real_agent", "label": "x"},
        headers=headers,
    )
    assert res.status_code == 404


async def test_cannot_create_key_for_uninstalled_agent(client, unique_email):
    headers = await _auth_headers(client, unique_email)
    await client.post(
        "/api/v1/marketplace/agents/tolemate_service_booking_agent/uninstall", headers=headers
    )
    res = await client.post(
        "/api/v1/integrations/api-keys",
        json={"agent_slug": "tolemate_service_booking_agent", "label": "x"},
        headers=headers,
    )
    assert res.status_code == 409


async def test_non_admin_cannot_manage_api_keys(client, unique_email):
    from sqlalchemy import select

    from app.db.session import async_session_factory
    from app.models.user import Role, User

    headers = await _auth_headers(client, unique_email)
    async with async_session_factory() as db:
        result = await db.execute(select(User).where(User.email == unique_email))
        user = result.scalar_one()
        user.role = Role.VIEWER
        db.add(user)
        await db.commit()

    res = await client.post(
        "/api/v1/integrations/api-keys",
        json={"agent_slug": "general_assistant", "label": "x"},
        headers=headers,
    )
    assert res.status_code == 403


async def test_api_keys_are_tenant_isolated(client, unique_email):
    tenant_a_headers = await _auth_headers(client, unique_email)
    tenant_b_headers = await _auth_headers(client, f"b-{unique_email}")

    await client.post(
        "/api/v1/integrations/api-keys",
        json={"agent_slug": "general_assistant", "label": "tenant A key"},
        headers=tenant_a_headers,
    )

    b_keys = await client.get("/api/v1/integrations/api-keys", headers=tenant_b_headers)
    assert b_keys.json() == []
