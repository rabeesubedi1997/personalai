import pytest

from app.services.ai.base import GenerationResult, ToolCall
from tests.fakes import FakeAIProvider

pytestmark = pytest.mark.asyncio


async def _auth_headers(client, email: str) -> dict:
    await client.post("/api/v1/auth/bootstrap", json={"email": email, "password": "pw123456"})
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "pw123456"})
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_ghar_nepal_agent_is_listed(client, unique_email):
    headers = await _auth_headers(client, unique_email)
    res = await client.get("/api/v1/agents", headers=headers)
    names = [a["name"] for a in res.json()]
    assert "ghar_nepal_property_agent" in names


async def test_search_then_enquiry_workflow(client, unique_email, monkeypatch):
    fake = FakeAIProvider(
        [
            GenerationResult(
                content="",
                tool_calls=[
                    ToolCall(
                        id="1",
                        name="search_properties",
                        arguments={"property_type": "apartment", "location": "Lalitpur"},
                    )
                ],
                model="fake",
            ),
            GenerationResult(
                content="",
                tool_calls=[
                    ToolCall(
                        id="2",
                        name="create_property_enquiry",
                        arguments={
                            "property_id": "GN-001",
                            "customer_name": "Sita Gurung",
                            "message": "Interested, please contact me.",
                        },
                    )
                ],
                model="fake",
            ),
            GenerationResult(content="Your enquiry has been submitted.", model="fake"),
        ]
    )
    monkeypatch.setattr("app.services.agent_execution.get_ai_provider", lambda: fake)
    headers = await _auth_headers(client, unique_email)

    res = await client.post(
        "/api/v1/agents/run",
        json={
            "agent": "ghar_nepal_property_agent",
            "message": "I'm looking for an apartment in Lalitpur, please submit an enquiry for Sita Gurung",
        },
        headers=headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "completed"
    assert len(body["tool_trace"]) == 2
    assert body["tool_trace"][0]["tool"] == "search_properties"
    assert body["tool_trace"][1]["tool"] == "create_property_enquiry"
    assert body["tool_trace"][1]["is_error"] is False
    assert "GN-ENQ-" in body["tool_trace"][1]["result"]


async def test_viewing_request_on_sold_property_reported_honestly(
    client, unique_email, monkeypatch
):
    fake = FakeAIProvider(
        [
            GenerationResult(
                content="",
                tool_calls=[
                    ToolCall(
                        id="1",
                        name="create_viewing_request",
                        arguments={
                            "property_id": "GN-003",
                            "customer_name": "Sita Gurung",
                            "preferred_date": "2026-10-15",
                        },
                    )
                ],
                model="fake",
            ),
            GenerationResult(content="That property is no longer available.", model="fake"),
        ]
    )
    monkeypatch.setattr("app.services.agent_execution.get_ai_provider", lambda: fake)
    headers = await _auth_headers(client, unique_email)

    res = await client.post(
        "/api/v1/agents/run",
        json={
            "agent": "ghar_nepal_property_agent",
            "message": "Request a viewing for GN-003",
        },
        headers=headers,
    )
    body = res.json()
    assert body["tool_trace"][0]["is_error"] is True
    assert "not currently available" in body["tool_trace"][0]["result"].lower()


async def test_ghar_nepal_cancel_viewing_requires_approval(client, unique_email, monkeypatch):
    # Reuses the same generic cancel_booking approval flow already proven
    # for Tolemate — a viewing cancellation is just a different booking_id.
    fake = FakeAIProvider(
        [
            GenerationResult(
                content="",
                tool_calls=[
                    ToolCall(
                        id="1", name="cancel_booking", arguments={"booking_id": "GN-VIEW-ABC123"}
                    )
                ],
                model="fake",
            ),
        ]
    )
    monkeypatch.setattr("app.services.agent_execution.get_ai_provider", lambda: fake)
    headers = await _auth_headers(client, unique_email)

    res = await client.post(
        "/api/v1/agents/run",
        json={
            "agent": "ghar_nepal_property_agent",
            "message": "Cancel viewing GN-VIEW-ABC123",
        },
        headers=headers,
    )
    body = res.json()
    assert body["status"] == "awaiting_approval"
    assert body["approval_id"] is not None
