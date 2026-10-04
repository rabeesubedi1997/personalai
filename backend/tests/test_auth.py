import pytest

pytestmark = pytest.mark.asyncio


async def test_bootstrap_then_login(client, unique_email):
    bootstrap = await client.post(
        "/api/v1/auth/bootstrap", json={"email": unique_email, "password": "Sup3rSecret!"}
    )
    assert bootstrap.status_code == 201
    assert bootstrap.json()["email"] == unique_email

    login = await client.post(
        "/api/v1/auth/login", json={"email": unique_email, "password": "Sup3rSecret!"}
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    assert token

    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert me.status_code == 200
    assert me.json()["email"] == unique_email


async def test_login_wrong_password_rejected(client, unique_email):
    await client.post(
        "/api/v1/auth/bootstrap", json={"email": unique_email, "password": "Sup3rSecret!"}
    )
    login = await client.post(
        "/api/v1/auth/login", json={"email": unique_email, "password": "wrong"}
    )
    assert login.status_code == 401


async def test_me_requires_token(client):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


async def test_duplicate_bootstrap_rejected(client, unique_email):
    first = await client.post(
        "/api/v1/auth/bootstrap", json={"email": unique_email, "password": "pw123456"}
    )
    assert first.status_code == 201
    second = await client.post(
        "/api/v1/auth/bootstrap", json={"email": unique_email, "password": "pw123456"}
    )
    assert second.status_code == 409
