"""
Proves the actual end-to-end switch: once a tenant configures a real
Tolemate connector (via PUT /api/v1/business-connectors/tolemate), an
agent run's search_service_providers tool call hits that real connector
instead of the mock — with zero change to the agent, the orchestrator, or
how the run is triggered. A tenant that never configures one (every other
test in this suite) keeps getting the mock, proving the default behavior
is unchanged.
"""
import httpx
import pytest

from app.services.ai.base import GenerationResult, ToolCall
from tests.fakes import FakeAIProvider

pytestmark = pytest.mark.asyncio


async def _auth_headers(client, email: str) -> dict:
    await client.post("/api/v1/auth/bootstrap", json={"email": email, "password": "pw123456"})
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "pw123456"})
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_agent_run_uses_real_connector_once_configured(client, unique_email, monkeypatch):
    async def fake_get(self, url, params=None, **kwargs):
        assert url.endswith("/api/services/search")
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": 7,
                        "name": "Deep House Cleaning",
                        "price": 200,
                        "vendor": {
                            "id": 2,
                            "business_name": "Sparkling Clean Services",
                            "rating": 4.9,
                            "user": {"lat": 27.7172, "lng": 85.3240},
                        },
                    }
                ]
            },
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    fake_ai = FakeAIProvider(
        [
            GenerationResult(
                content="",
                tool_calls=[
                    ToolCall(
                        id="1",
                        name="search_service_providers",
                        arguments={"service": "deep house cleaning", "location": "Kathmandu"},
                    )
                ],
                model="fake",
            ),
            GenerationResult(content="Found it.", model="fake"),
        ]
    )
    monkeypatch.setattr("app.services.agent_execution.get_ai_provider", lambda: fake_ai)

    headers = await _auth_headers(client, unique_email)
    await client.put(
        "/api/v1/business-connectors/tolemate",
        json={"base_url": "http://tolemate.test"},
        headers=headers,
    )

    res = await client.post(
        "/api/v1/agents/run",
        json={
            "agent": "tolemate_service_booking_agent",
            "message": "I need deep house cleaning in Kathmandu",
        },
        headers=headers,
    )
    assert res.status_code == 200
    body = res.json()
    result = body["tool_trace"][0]["result"]
    assert "Sparkling Clean Services" in result
    assert "Kathmandu" in result


async def test_other_tenant_without_config_still_gets_mock(client, unique_email, monkeypatch):
    fake_ai = FakeAIProvider(
        [
            GenerationResult(
                content="",
                tool_calls=[
                    ToolCall(
                        id="1",
                        name="search_service_providers",
                        arguments={"service": "electrician", "location": "Lalitpur"},
                    )
                ],
                model="fake",
            ),
            GenerationResult(content="Found it.", model="fake"),
        ]
    )
    monkeypatch.setattr("app.services.agent_execution.get_ai_provider", lambda: fake_ai)

    headers = await _auth_headers(client, unique_email)
    res = await client.post(
        "/api/v1/agents/run",
        json={"agent": "tolemate_service_booking_agent", "message": "electrician in Lalitpur"},
        headers=headers,
    )
    assert res.status_code == 200
    assert "Bikash Electrical Services" in res.json()["tool_trace"][0]["result"]
