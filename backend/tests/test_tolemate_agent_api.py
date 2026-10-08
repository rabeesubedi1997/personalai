"""
Full Tolemate booking workflow through the real API — the Phase 6
demonstration from the master spec (Section 50's example, scaled down to
what's actually built): find a provider, check availability, book, and
confirm cancellation requires approval.
"""
from datetime import date

import pytest

from app.services.ai.base import GenerationResult, ToolCall
from tests.fakes import FakeAIProvider

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _pin_today(monkeypatch):
    # The mock providers' availability is fixed to dates in October 2026, and
    # the booking tools now reject past dates — so pin "today" or these tests
    # would start failing the day after the mock dates go by.
    monkeypatch.setattr("app.connectors.tolemate.tools._today", lambda: date(2026, 10, 5))


async def _auth_headers(client, email: str) -> dict:
    await client.post("/api/v1/auth/bootstrap", json={"email": email, "password": "pw123456"})
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "pw123456"})
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_tolemate_agent_is_listed(client, unique_email):
    headers = await _auth_headers(client, unique_email)
    res = await client.get("/api/v1/agents", headers=headers)
    names = [a["name"] for a in res.json()]
    assert "tolemate_service_booking_agent" in names


async def test_full_search_check_book_workflow(client, unique_email, monkeypatch):
    fake = FakeAIProvider(
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
            GenerationResult(
                content="",
                tool_calls=[
                    ToolCall(
                        id="2",
                        name="check_provider_availability",
                        arguments={"provider_id": "PRV-001", "date": "2026-10-10"},
                    )
                ],
                model="fake",
            ),
            GenerationResult(
                content="",
                tool_calls=[
                    ToolCall(
                        id="3",
                        name="create_service_booking",
                        arguments={
                            "provider_id": "PRV-001",
                            "date": "2026-10-10",
                            "customer_name": "Ram Shrestha",
                        },
                    )
                ],
                model="fake",
            ),
            GenerationResult(content="Your booking is confirmed.", model="fake"),
        ]
    )
    monkeypatch.setattr("app.services.agent_execution.get_ai_provider", lambda: fake)
    headers = await _auth_headers(client, unique_email)

    res = await client.post(
        "/api/v1/agents/run",
        json={
            "agent": "tolemate_service_booking_agent",
            "message": "Book an electrician in Lalitpur for Oct 10 for Ram Shrestha",
        },
        headers=headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "completed"
    assert len(body["tool_trace"]) == 3
    assert body["tool_trace"][0]["tool"] == "search_service_providers"
    assert body["tool_trace"][1]["tool"] == "check_provider_availability"
    assert body["tool_trace"][2]["tool"] == "create_service_booking"
    assert body["tool_trace"][2]["is_error"] is False
    assert "TOLEMATE-" in body["tool_trace"][2]["result"]


async def test_booking_unavailable_date_reported_as_tool_error_not_fabricated_success(
    client, unique_email, monkeypatch
):
    fake = FakeAIProvider(
        [
            GenerationResult(
                content="",
                tool_calls=[
                    ToolCall(
                        id="1",
                        name="create_service_booking",
                        arguments={
                            "provider_id": "PRV-001",
                            "date": "2099-01-01",
                            "customer_name": "Ram Shrestha",
                        },
                    )
                ],
                model="fake",
            ),
            GenerationResult(content="That date isn't available.", model="fake"),
        ]
    )
    monkeypatch.setattr("app.services.agent_execution.get_ai_provider", lambda: fake)
    headers = await _auth_headers(client, unique_email)

    res = await client.post(
        "/api/v1/agents/run",
        json={
            "agent": "tolemate_service_booking_agent",
            "message": "Book PRV-001 for 2099-01-01",
        },
        headers=headers,
    )
    body = res.json()
    assert body["tool_trace"][0]["is_error"] is True
    assert "not available" in body["tool_trace"][0]["result"].lower()


async def test_tolemate_cancel_booking_requires_approval(client, unique_email, monkeypatch):
    # Reuses the platform's generic approval-gated cancel_booking tool —
    # same mechanism proven in Phase 5, now used by a real business agent.
    fake = FakeAIProvider(
        [
            GenerationResult(
                content="",
                tool_calls=[
                    ToolCall(
                        id="1", name="cancel_booking", arguments={"booking_id": "TOLEMATE-ABC123"}
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
            "agent": "tolemate_service_booking_agent",
            "message": "Cancel booking TOLEMATE-ABC123",
        },
        headers=headers,
    )
    body = res.json()
    assert body["status"] == "awaiting_approval"
    assert body["approval_id"] is not None
