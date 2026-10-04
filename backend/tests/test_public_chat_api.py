"""
Tests for the public, API-key-authenticated chat endpoint — the one meant
to be embedded on an external site, not called by the dashboard.
"""
import pytest

from app.services.ai.base import GenerationResult
from tests.fakes import FakeAIProvider

pytestmark = pytest.mark.asyncio


async def _auth_headers(client, email: str) -> dict:
    await client.post("/api/v1/auth/bootstrap", json={"email": email, "password": "pw123456"})
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "pw123456"})
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _create_key(client, headers, agent_slug="general_assistant") -> str:
    res = await client.post(
        "/api/v1/integrations/api-keys",
        json={"agent_slug": agent_slug, "label": "test widget"},
        headers=headers,
    )
    return res.json()["api_key"]


async def test_public_chat_requires_api_key(client):
    res = await client.post("/api/v1/public/chat", json={"message": "hi"})
    assert res.status_code == 401


async def test_public_chat_rejects_invalid_key(client):
    res = await client.post(
        "/api/v1/public/chat",
        json={"message": "hi"},
        headers={"X-API-Key": "pak_not_a_real_key"},
    )
    assert res.status_code == 401


async def test_public_chat_works_with_valid_key(client, unique_email, monkeypatch):
    fake = FakeAIProvider([GenerationResult(content="Hello from the widget!", model="fake")])
    monkeypatch.setattr("app.services.agent_execution.get_ai_provider", lambda: fake)

    headers = await _auth_headers(client, unique_email)
    api_key = await _create_key(client, headers)

    res = await client.post(
        "/api/v1/public/chat",
        json={"message": "hi there"},
        headers={"X-API-Key": api_key},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "completed"
    assert body["final_response"] == "Hello from the widget!"
    assert body["conversation_id"] is not None


async def test_public_chat_sets_permissive_cors_headers(client, unique_email, monkeypatch):
    fake = FakeAIProvider([GenerationResult(content="hi", model="fake")])
    monkeypatch.setattr("app.services.agent_execution.get_ai_provider", lambda: fake)
    headers = await _auth_headers(client, unique_email)
    api_key = await _create_key(client, headers)

    res = await client.post(
        "/api/v1/public/chat",
        json={"message": "hi"},
        headers={"X-API-Key": api_key, "Origin": "https://some-arbitrary-external-site.example"},
    )
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == "*"


async def test_revoked_key_is_rejected(client, unique_email, monkeypatch):
    fake = FakeAIProvider([GenerationResult(content="hi", model="fake")])
    monkeypatch.setattr("app.services.agent_execution.get_ai_provider", lambda: fake)
    headers = await _auth_headers(client, unique_email)
    api_key = await _create_key(client, headers)

    list_res = await client.get("/api/v1/integrations/api-keys", headers=headers)
    key_id = list_res.json()[0]["id"]
    await client.delete(f"/api/v1/integrations/api-keys/{key_id}", headers=headers)

    res = await client.post(
        "/api/v1/public/chat", json={"message": "hi"}, headers={"X-API-Key": api_key}
    )
    assert res.status_code == 401


async def test_public_chat_continues_conversation(client, unique_email, monkeypatch):
    fake = FakeAIProvider(
        [
            GenerationResult(content="What's your name?", model="fake"),
            GenerationResult(content="Nice to meet you!", model="fake"),
        ]
    )
    monkeypatch.setattr("app.services.agent_execution.get_ai_provider", lambda: fake)
    headers = await _auth_headers(client, unique_email)
    api_key = await _create_key(client, headers)

    first = await client.post(
        "/api/v1/public/chat", json={"message": "hi"}, headers={"X-API-Key": api_key}
    )
    conversation_id = first.json()["conversation_id"]

    second = await client.post(
        "/api/v1/public/chat",
        json={"message": "It's Sam", "conversation_id": conversation_id},
        headers={"X-API-Key": api_key},
    )
    assert second.status_code == 200
    second_messages = fake.received_messages[1]
    contents = " ".join(m.content for m in second_messages)
    assert "hi" in contents.lower()
    assert "It's Sam" in contents


async def test_public_chat_usage_counts_toward_tenant_billing(client, unique_email, monkeypatch):
    fake = FakeAIProvider([GenerationResult(content="hi", model="fake")])
    monkeypatch.setattr("app.services.agent_execution.get_ai_provider", lambda: fake)
    headers = await _auth_headers(client, unique_email)
    api_key = await _create_key(client, headers)

    await client.post(
        "/api/v1/public/chat", json={"message": "hi"}, headers={"X-API-Key": api_key}
    )

    sub_res = await client.get("/api/v1/billing/subscription", headers=headers)
    assert sub_res.json()["current_period_agent_runs"] == 1


async def test_public_chat_key_is_scoped_to_its_own_agent(client, unique_email, monkeypatch):
    fake = FakeAIProvider([GenerationResult(content="hi", model="fake")])
    monkeypatch.setattr("app.services.agent_execution.get_ai_provider", lambda: fake)
    headers = await _auth_headers(client, unique_email)
    # Key issued for general_assistant...
    api_key = await _create_key(client, headers, agent_slug="general_assistant")

    # ...cannot be redirected to run a different agent — the endpoint
    # always uses the agent baked into the key, never a caller-supplied one.
    res = await client.post(
        "/api/v1/public/chat", json={"message": "hi"}, headers={"X-API-Key": api_key}
    )
    assert res.json()["agent"] == "general_assistant"


async def test_public_chat_tenant_isolation(client, unique_email, monkeypatch):
    fake = FakeAIProvider([GenerationResult(content="tenant A's answer", model="fake")])
    monkeypatch.setattr("app.services.agent_execution.get_ai_provider", lambda: fake)

    tenant_a_headers = await _auth_headers(client, unique_email)
    tenant_b_headers = await _auth_headers(client, f"b-{unique_email}")

    key_a = await _create_key(client, tenant_a_headers)

    # Running tenant A's key must not show up in tenant B's run history.
    await client.post("/api/v1/public/chat", json={"message": "hi"}, headers={"X-API-Key": key_a})

    b_runs = await client.get("/api/v1/agents/runs", headers=tenant_b_headers)
    assert b_runs.json() == []
