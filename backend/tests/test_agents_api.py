import pytest

from app.services.ai.base import GenerationResult, ToolCall
from tests.fakes import FakeAIProvider

pytestmark = pytest.mark.asyncio


async def _auth_headers(client, email: str) -> dict:
    await client.post("/api/v1/auth/bootstrap", json={"email": email, "password": "pw123456"})
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "pw123456"})
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_list_agents_and_tools_require_auth(client):
    assert (await client.get("/api/v1/agents")).status_code == 401
    assert (await client.get("/api/v1/tools")).status_code == 401


async def test_list_agents_and_tools(client, unique_email):
    headers = await _auth_headers(client, unique_email)

    agents_res = await client.get("/api/v1/agents", headers=headers)
    assert agents_res.status_code == 200
    names = [a["name"] for a in agents_res.json()]
    assert "general_assistant" in names

    tools_res = await client.get("/api/v1/tools", headers=headers)
    assert tools_res.status_code == 200
    tool_names = [t["name"] for t in tools_res.json()]
    assert "get_current_time" in tool_names


async def test_run_unknown_agent_returns_404(client, unique_email):
    headers = await _auth_headers(client, unique_email)
    res = await client.post(
        "/api/v1/agents/run", json={"agent": "nonexistent", "message": "hi"}, headers=headers
    )
    assert res.status_code == 404


async def test_run_agent_executes_tool_and_persists_run(client, unique_email, monkeypatch):
    fake = FakeAIProvider(
        [
            GenerationResult(
                content="",
                tool_calls=[ToolCall(id="1", name="get_current_time", arguments={})],
                model="fake-qwen",
            ),
            GenerationResult(content="The current time was retrieved.", model="fake-qwen"),
        ]
    )
    monkeypatch.setattr("app.services.agent_execution.get_ai_provider", lambda: fake)

    headers = await _auth_headers(client, unique_email)
    res = await client.post(
        "/api/v1/agents/run",
        json={"agent": "general_assistant", "message": "what time is it?"},
        headers=headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "completed"
    assert body["final_response"] == "The current time was retrieved."
    assert len(body["tool_trace"]) == 1
    assert body["tool_trace"][0]["tool"] == "get_current_time"
    assert body["model"] == "fake-qwen"
