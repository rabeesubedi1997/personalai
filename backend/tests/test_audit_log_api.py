import pytest

from app.services.ai.base import GenerationResult, ToolCall
from tests.fakes import FakeAIProvider

pytestmark = pytest.mark.asyncio


async def _auth_headers(client, email: str) -> dict:
    await client.post("/api/v1/auth/bootstrap", json={"email": email, "password": "pw123456"})
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "pw123456"})
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_denied_tool_call_is_audited(client, unique_email, monkeypatch):
    fake = FakeAIProvider(
        [
            GenerationResult(
                content="",
                tool_calls=[ToolCall(id="1", name="delete_everything", arguments={})],
                model="fake",
            ),
            GenerationResult(content="cannot do that", model="fake"),
        ]
    )
    monkeypatch.setattr("app.api.v1.agents.get_ai_provider", lambda: fake)
    headers = await _auth_headers(client, unique_email)
    await client.post(
        "/api/v1/agents/run",
        json={"agent": "general_assistant", "message": "delete everything"},
        headers=headers,
    )

    audit_res = await client.get(
        "/api/v1/audit-logs", params={"event_type": "tool_call_denied"}, headers=headers
    )
    assert audit_res.status_code == 200
    entries = audit_res.json()
    assert len(entries) == 1
    assert entries[0]["tool_name"] == "delete_everything"
    assert entries[0]["status"] == "denied"


async def test_approval_decision_is_audited(client, unique_email, monkeypatch):
    fake = FakeAIProvider(
        [
            GenerationResult(
                content="",
                tool_calls=[
                    ToolCall(id="1", name="cancel_booking", arguments={"booking_id": "BK-9"})
                ],
                model="fake",
            ),
        ]
    )
    monkeypatch.setattr("app.api.v1.agents.get_ai_provider", lambda: fake)
    headers = await _auth_headers(client, unique_email)
    run_res = await client.post(
        "/api/v1/agents/run",
        json={"agent": "general_assistant", "message": "cancel booking BK-9"},
        headers=headers,
    )
    approval_id = run_res.json()["approval_id"]
    await client.post(f"/api/v1/approvals/{approval_id}/approve", json={}, headers=headers)

    audit_res = await client.get(
        "/api/v1/audit-logs", params={"event_type": "approval_executed"}, headers=headers
    )
    entries = audit_res.json()
    assert len(entries) == 1
    assert entries[0]["approval_id"] == approval_id


async def test_audit_logs_require_auth(client):
    assert (await client.get("/api/v1/audit-logs")).status_code == 401


async def test_audit_logs_are_tenant_isolated(client, unique_email, monkeypatch):
    fake = FakeAIProvider(
        [
            GenerationResult(
                content="",
                tool_calls=[ToolCall(id="1", name="delete_everything", arguments={})],
                model="fake",
            ),
            GenerationResult(content="cannot do that", model="fake"),
        ]
    )
    monkeypatch.setattr("app.api.v1.agents.get_ai_provider", lambda: fake)
    tenant_a_headers = await _auth_headers(client, unique_email)
    tenant_b_headers = await _auth_headers(client, f"b-{unique_email}")

    await client.post(
        "/api/v1/agents/run",
        json={"agent": "general_assistant", "message": "delete everything"},
        headers=tenant_a_headers,
    )

    b_logs = await client.get("/api/v1/audit-logs", headers=tenant_b_headers)
    assert b_logs.json() == []
