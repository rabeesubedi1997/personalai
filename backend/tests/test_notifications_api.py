"""
API-level tests, including the real integration: an approval-gated tool
call must notify the requester, and resolving it must notify them again.
"""
import pytest

from app.services.ai.base import GenerationResult, ToolCall
from tests.fakes import FakeAIProvider

pytestmark = pytest.mark.asyncio


async def _auth_headers(client, email: str) -> dict:
    await client.post("/api/v1/auth/bootstrap", json={"email": email, "password": "pw123456"})
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "pw123456"})
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_notifications_require_auth(client):
    assert (await client.get("/api/v1/notifications")).status_code == 401


async def test_approval_request_notifies_requester(client, unique_email, monkeypatch):
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
    headers = await _auth_headers(client, unique_email)

    run_res = await client.post(
        "/api/v1/agents/run",
        json={"agent": "general_assistant", "message": "cancel booking BK-1"},
        headers=headers,
    )
    assert run_res.json()["status"] == "awaiting_approval"

    notif_res = await client.get("/api/v1/notifications", headers=headers)
    assert notif_res.status_code == 200
    notifications = notif_res.json()
    assert len(notifications) == 1
    assert notifications[0]["channel"] == "web"
    assert "pending" in notifications[0]["message"].lower()
    assert notifications[0]["is_read"] is False


async def test_approving_notifies_requester_of_outcome(client, unique_email, monkeypatch):
    fake = FakeAIProvider(
        [
            GenerationResult(
                content="",
                tool_calls=[
                    ToolCall(id="1", name="cancel_booking", arguments={"booking_id": "BK-2"})
                ],
                model="fake",
            ),
        ]
    )
    monkeypatch.setattr("app.api.v1.agents.get_ai_provider", lambda: fake)
    headers = await _auth_headers(client, unique_email)

    run_res = await client.post(
        "/api/v1/agents/run",
        json={"agent": "general_assistant", "message": "cancel booking BK-2"},
        headers=headers,
    )
    approval_id = run_res.json()["approval_id"]

    await client.post(f"/api/v1/approvals/{approval_id}/approve", json={}, headers=headers)

    notif_res = await client.get("/api/v1/notifications", headers=headers)
    notifications = notif_res.json()
    # One for the pending request, one for the resolution.
    assert len(notifications) == 2
    subjects = [n["subject"] for n in notifications]
    assert "Approval decided" in subjects
    decided = next(n for n in notifications if n["subject"] == "Approval decided")
    assert "approved and completed" in decided["message"]


async def test_rejecting_notifies_requester(client, unique_email, monkeypatch):
    fake = FakeAIProvider(
        [
            GenerationResult(
                content="",
                tool_calls=[
                    ToolCall(id="1", name="cancel_booking", arguments={"booking_id": "BK-3"})
                ],
                model="fake",
            ),
        ]
    )
    monkeypatch.setattr("app.api.v1.agents.get_ai_provider", lambda: fake)
    headers = await _auth_headers(client, unique_email)

    run_res = await client.post(
        "/api/v1/agents/run",
        json={"agent": "general_assistant", "message": "cancel booking BK-3"},
        headers=headers,
    )
    approval_id = run_res.json()["approval_id"]

    await client.post(
        f"/api/v1/approvals/{approval_id}/reject",
        json={"note": "not actually requested"},
        headers=headers,
    )

    notif_res = await client.get("/api/v1/notifications", headers=headers)
    decided = next(n for n in notif_res.json() if n["subject"] == "Approval decided")
    assert "rejected" in decided["message"].lower()
    assert "not actually requested" in decided["message"]


async def test_mark_notification_read(client, unique_email, monkeypatch):
    fake = FakeAIProvider(
        [
            GenerationResult(
                content="",
                tool_calls=[
                    ToolCall(id="1", name="cancel_booking", arguments={"booking_id": "BK-4"})
                ],
                model="fake",
            ),
        ]
    )
    monkeypatch.setattr("app.api.v1.agents.get_ai_provider", lambda: fake)
    headers = await _auth_headers(client, unique_email)

    await client.post(
        "/api/v1/agents/run",
        json={"agent": "general_assistant", "message": "cancel booking BK-4"},
        headers=headers,
    )
    notifications = (await client.get("/api/v1/notifications", headers=headers)).json()
    notification_id = notifications[0]["id"]

    read_res = await client.post(
        f"/api/v1/notifications/{notification_id}/read", headers=headers
    )
    assert read_res.status_code == 200
    assert read_res.json()["is_read"] is True

    unread = (
        await client.get(
            "/api/v1/notifications", params={"unread_only": True}, headers=headers
        )
    ).json()
    assert unread == []


async def test_notifications_are_tenant_isolated(client, unique_email, monkeypatch):
    fake = FakeAIProvider(
        [
            GenerationResult(
                content="",
                tool_calls=[
                    ToolCall(id="1", name="cancel_booking", arguments={"booking_id": "BK-5"})
                ],
                model="fake",
            ),
        ]
    )
    monkeypatch.setattr("app.api.v1.agents.get_ai_provider", lambda: fake)
    tenant_a_headers = await _auth_headers(client, unique_email)
    tenant_b_headers = await _auth_headers(client, f"b-{unique_email}")

    await client.post(
        "/api/v1/agents/run",
        json={"agent": "general_assistant", "message": "cancel booking BK-5"},
        headers=tenant_a_headers,
    )

    b_notifications = await client.get("/api/v1/notifications", headers=tenant_b_headers)
    assert b_notifications.json() == []
