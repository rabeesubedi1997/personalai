import pytest

pytestmark = pytest.mark.asyncio


async def test_health_endpoint(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"


async def test_root(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "running"
