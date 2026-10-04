import pytest

from app.services.ai.base import GenerationResult, ToolCall
from tests.fakes import FakeAIProvider

pytestmark = pytest.mark.asyncio


async def _auth_headers(client, email: str) -> dict:
    await client.post("/api/v1/auth/bootstrap", json={"email": email, "password": "pw123456"})
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "pw123456"})
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _request_cancel_booking(client, headers, monkeypatch) -> dict:
    fake = FakeAIProvider(
        [
            GenerationResult(
                content="",
                tool_calls=[
                    ToolCall(id="1", name="cancel_booking", arguments={"booking_id": "BK-1"})
                ],
                model="fake",
            ),
        ]
    )
    monkeypatch.setattr("app.api.v1.agents.get_ai_provider", lambda: fake)
    res = await client.post(
        "/api/v1/agents/run",
        json={"agent": "general_assistant", "message": "cancel booking BK-1"},
        headers=headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "awaiting_approval"
    assert body["approval_id"] is not None
    return body


async def test_sensitive_tool_creates_pending_approval_not_executed(
    client, unique_email, monkeypatch
):
    headers = await _auth_headers(client, unique_email)
    body = await _request_cancel_booking(client, headers, monkeypatch)

    approval_res = await client.get(f"/api/v1/approvals/{body['approval_id']}", headers=headers)
    assert approval_res.status_code == 200
    approval = approval_res.json()
    assert approval["status"] == "pending"
    assert approval["tool_name"] == "cancel_booking"
    assert approval["result"] is None


async def test_approve_executes_the_tool(client, unique_email, monkeypatch):
    headers = await _auth_headers(client, unique_email)
    body = await _request_cancel_booking(client, headers, monkeypatch)

    approve_res = await client.post(
        f"/api/v1/approvals/{body['approval_id']}/approve",
        json={"note": "confirmed with customer"},
        headers=headers,
    )
    assert approve_res.status_code == 200
    approved = approve_res.json()
    assert approved["status"] == "executed"
    assert approved["result"]["data"]["cancelled"] is True
    assert approved["decision_note"] == "confirmed with customer"


async def test_reject_does_not_execute_the_tool(client, unique_email, monkeypatch):
    headers = await _auth_headers(client, unique_email)
    body = await _request_cancel_booking(client, headers, monkeypatch)

    reject_res = await client.post(
        f"/api/v1/approvals/{body['approval_id']}/reject",
        json={"note": "customer did not actually ask for this"},
        headers=headers,
    )
    assert reject_res.status_code == 200
    rejected = reject_res.json()
    assert rejected["status"] == "rejected"
    assert rejected["result"] is None


async def test_cannot_decide_an_already_decided_approval(client, unique_email, monkeypatch):
    headers = await _auth_headers(client, unique_email)
    body = await _request_cancel_booking(client, headers, monkeypatch)

    await client.post(
        f"/api/v1/approvals/{body['approval_id']}/approve", json={}, headers=headers
    )
    second = await client.post(
        f"/api/v1/approvals/{body['approval_id']}/approve", json={}, headers=headers
    )
    assert second.status_code == 409


async def test_approval_is_tenant_isolated(client, unique_email, monkeypatch):
    tenant_a_headers = await _auth_headers(client, unique_email)
    tenant_b_headers = await _auth_headers(client, f"b-{unique_email}")

    body = await _request_cancel_booking(client, tenant_a_headers, monkeypatch)

    # Tenant B must not see or act on tenant A's approval.
    get_res = await client.get(
        f"/api/v1/approvals/{body['approval_id']}", headers=tenant_b_headers
    )
    assert get_res.status_code == 404

    approve_res = await client.post(
        f"/api/v1/approvals/{body['approval_id']}/approve", json={}, headers=tenant_b_headers
    )
    assert approve_res.status_code == 404

    list_res = await client.get("/api/v1/approvals", headers=tenant_b_headers)
    assert list_res.json() == []


async def test_approvals_require_auth(client):
    assert (await client.get("/api/v1/approvals")).status_code == 401
