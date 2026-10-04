import pytest

from tests.fakes import FakeAIProvider

pytestmark = pytest.mark.asyncio


def _keyword_embed(text: str) -> list[float]:
    vocab = ["electrician", "plumber", "hours"]
    lowered = text.lower()
    return [1.0 if word in lowered else 0.0 for word in vocab]


async def _auth_headers(client, email: str) -> dict:
    await client.post("/api/v1/auth/bootstrap", json={"email": email, "password": "pw123456"})
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "pw123456"})
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _patch_embedder(monkeypatch):
    fake = FakeAIProvider(responses=[], embed_fn=_keyword_embed)
    monkeypatch.setattr("app.api.v1.memory.get_ai_provider", lambda: fake)
    return fake


async def test_memory_requires_auth(client):
    assert (await client.get("/api/v1/memory")).status_code == 401
    assert (
        await client.post("/api/v1/memory", json={"memory_type": "knowledge", "content": "x"})
    ).status_code == 401


async def test_create_and_list_memory(client, unique_email, monkeypatch):
    _patch_embedder(monkeypatch)
    headers = await _auth_headers(client, unique_email)

    create_res = await client.post(
        "/api/v1/memory",
        json={"memory_type": "knowledge", "content": "Electricians serve Lalitpur."},
        headers=headers,
    )
    assert create_res.status_code == 201
    assert create_res.json()["content"] == "Electricians serve Lalitpur."

    list_res = await client.get(
        "/api/v1/memory", params={"memory_type": "knowledge"}, headers=headers
    )
    assert list_res.status_code == 200
    assert len(list_res.json()) == 1


async def test_search_memory_returns_scored_results(client, unique_email, monkeypatch):
    _patch_embedder(monkeypatch)
    headers = await _auth_headers(client, unique_email)

    await client.post(
        "/api/v1/memory",
        json={"memory_type": "knowledge", "content": "Electricians serve Lalitpur."},
        headers=headers,
    )
    await client.post(
        "/api/v1/memory",
        json={"memory_type": "knowledge", "content": "Plumbers available on weekends."},
        headers=headers,
    )

    search_res = await client.post(
        "/api/v1/memory/search",
        json={"query": "I need an electrician", "top_k": 1},
        headers=headers,
    )
    assert search_res.status_code == 200
    results = search_res.json()
    assert len(results) == 1
    assert "electrician" in results[0]["memory"]["content"].lower()
    assert results[0]["score"] > 0


async def test_memory_is_tenant_isolated(client, unique_email, monkeypatch):
    _patch_embedder(monkeypatch)
    tenant_a_headers = await _auth_headers(client, unique_email)
    tenant_b_headers = await _auth_headers(client, f"b-{unique_email}")

    await client.post(
        "/api/v1/memory",
        json={"memory_type": "knowledge", "content": "Tenant A secret electrician list."},
        headers=tenant_a_headers,
    )

    list_res = await client.get("/api/v1/memory", headers=tenant_b_headers)
    assert list_res.json() == []

    search_res = await client.post(
        "/api/v1/memory/search",
        json={"query": "electrician"},
        headers=tenant_b_headers,
    )
    assert search_res.json() == []
