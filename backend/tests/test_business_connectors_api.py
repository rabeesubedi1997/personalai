import pytest

pytestmark = pytest.mark.asyncio


async def _auth_headers(client, email: str) -> dict:
    await client.post("/api/v1/auth/bootstrap", json={"email": email, "password": "pw123456"})
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "pw123456"})
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_requires_auth(client):
    assert (await client.get("/api/v1/business-connectors")).status_code == 401


async def test_lists_all_registered_businesses_unconfigured_by_default(client, unique_email):
    headers = await _auth_headers(client, unique_email)
    res = await client.get("/api/v1/business-connectors", headers=headers)
    assert res.status_code == 200
    body = res.json()
    slugs = {b["business_slug"] for b in body}
    assert {"tolemate", "ghar_nepal", "paradise_nepal"} <= slugs
    assert all(b["connector"] is None for b in body)


async def test_set_and_list_connector(client, unique_email):
    headers = await _auth_headers(client, unique_email)
    res = await client.put(
        "/api/v1/business-connectors/tolemate",
        json={"base_url": "http://tolemate.test", "extra_config": {"default_radius_km": 20}},
        headers=headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["base_url"] == "http://tolemate.test"
    assert body["is_enabled"] is True
    assert body["extra_config"] == {"default_radius_km": 20}

    listing = await client.get("/api/v1/business-connectors", headers=headers)
    tolemate = next(b for b in listing.json() if b["business_slug"] == "tolemate")
    assert tolemate["connector"]["base_url"] == "http://tolemate.test"


async def test_set_unknown_business_404s(client, unique_email):
    headers = await _auth_headers(client, unique_email)
    res = await client.put(
        "/api/v1/business-connectors/not_a_real_business",
        json={"base_url": "http://example.com"},
        headers=headers,
    )
    assert res.status_code == 404


async def test_set_rejects_empty_base_url(client, unique_email):
    headers = await _auth_headers(client, unique_email)
    res = await client.put(
        "/api/v1/business-connectors/tolemate", json={"base_url": "  "}, headers=headers
    )
    assert res.status_code == 422


async def test_delete_connector_reverts_to_unconfigured(client, unique_email):
    headers = await _auth_headers(client, unique_email)
    await client.put(
        "/api/v1/business-connectors/tolemate",
        json={"base_url": "http://tolemate.test"},
        headers=headers,
    )
    res = await client.delete("/api/v1/business-connectors/tolemate", headers=headers)
    assert res.status_code == 204

    listing = await client.get("/api/v1/business-connectors", headers=headers)
    tolemate = next(b for b in listing.json() if b["business_slug"] == "tolemate")
    assert tolemate["connector"] is None


async def test_delete_unconfigured_connector_404s(client, unique_email):
    headers = await _auth_headers(client, unique_email)
    res = await client.delete("/api/v1/business-connectors/tolemate", headers=headers)
    assert res.status_code == 404


async def test_non_admin_cannot_manage_connectors(client, unique_email):
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

    res = await client.put(
        "/api/v1/business-connectors/tolemate",
        json={"base_url": "http://tolemate.test"},
        headers=headers,
    )
    assert res.status_code == 403


async def test_connector_config_is_tenant_isolated(client, unique_email):
    tenant_a_headers = await _auth_headers(client, unique_email)
    tenant_b_headers = await _auth_headers(client, f"b-{unique_email}")

    await client.put(
        "/api/v1/business-connectors/tolemate",
        json={"base_url": "http://tenant-a-only.test"},
        headers=tenant_a_headers,
    )

    listing_b = await client.get("/api/v1/business-connectors", headers=tenant_b_headers)
    tolemate_b = next(b for b in listing_b.json() if b["business_slug"] == "tolemate")
    assert tolemate_b["connector"] is None
