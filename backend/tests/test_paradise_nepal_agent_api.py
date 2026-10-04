import pytest

from app.services.ai.base import GenerationResult, ToolCall
from tests.fakes import FakeAIProvider

pytestmark = pytest.mark.asyncio


async def _auth_headers(client, email: str) -> dict:
    await client.post("/api/v1/auth/bootstrap", json={"email": email, "password": "pw123456"})
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "pw123456"})
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_paradise_nepal_agent_is_listed(client, unique_email):
    headers = await _auth_headers(client, unique_email)
    res = await client.get("/api/v1/agents", headers=headers)
    names = [a["name"] for a in res.json()]
    assert "paradise_nepal_hotel_agent" in names


async def test_full_search_check_book_workflow(client, unique_email, monkeypatch):
    fake = FakeAIProvider(
        [
            GenerationResult(
                content="",
                tool_calls=[
                    ToolCall(id="1", name="search_hotels", arguments={"location": "Pokhara"})
                ],
                model="fake",
            ),
            GenerationResult(
                content="",
                tool_calls=[
                    ToolCall(
                        id="2",
                        name="check_room_availability",
                        arguments={
                            "hotel_id": "PARADISE-H001",
                            "room_type": "deluxe",
                            "checkin": "2026-11-01",
                        },
                    )
                ],
                model="fake",
            ),
            GenerationResult(
                content="",
                tool_calls=[
                    ToolCall(
                        id="3",
                        name="create_hotel_booking",
                        arguments={
                            "hotel_id": "PARADISE-H001",
                            "room_type": "deluxe",
                            "checkin": "2026-11-01",
                            "checkout": "2026-11-03",
                            "guest_name": "Anil Rai",
                            "guests": 2,
                        },
                    )
                ],
                model="fake",
            ),
            GenerationResult(content="Your stay is booked.", model="fake"),
        ]
    )
    monkeypatch.setattr("app.api.v1.agents.get_ai_provider", lambda: fake)
    headers = await _auth_headers(client, unique_email)

    res = await client.post(
        "/api/v1/agents/run",
        json={
            "agent": "paradise_nepal_hotel_agent",
            "message": "Book a deluxe room in Pokhara for Nov 1-3 for Anil Rai, 2 guests",
        },
        headers=headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "completed"
    assert len(body["tool_trace"]) == 3
    assert body["tool_trace"][2]["tool"] == "create_hotel_booking"
    assert body["tool_trace"][2]["is_error"] is False
    assert "PARADISE-" in body["tool_trace"][2]["result"]


async def test_booking_unavailable_date_reported_honestly(client, unique_email, monkeypatch):
    fake = FakeAIProvider(
        [
            GenerationResult(
                content="",
                tool_calls=[
                    ToolCall(
                        id="1",
                        name="create_hotel_booking",
                        arguments={
                            "hotel_id": "PARADISE-H001",
                            "room_type": "deluxe",
                            "checkin": "2099-01-01",
                            "checkout": "2099-01-03",
                            "guest_name": "Anil Rai",
                        },
                    )
                ],
                model="fake",
            ),
            GenerationResult(content="That date is not available.", model="fake"),
        ]
    )
    monkeypatch.setattr("app.api.v1.agents.get_ai_provider", lambda: fake)
    headers = await _auth_headers(client, unique_email)

    res = await client.post(
        "/api/v1/agents/run",
        json={"agent": "paradise_nepal_hotel_agent", "message": "Book PARADISE-H001 for 2099-01-01"},
        headers=headers,
    )
    body = res.json()
    assert body["tool_trace"][0]["is_error"] is True
    assert "not available" in body["tool_trace"][0]["result"].lower()


async def test_paradise_nepal_cancel_booking_requires_approval(client, unique_email, monkeypatch):
    fake = FakeAIProvider(
        [
            GenerationResult(
                content="",
                tool_calls=[
                    ToolCall(
                        id="1", name="cancel_booking", arguments={"booking_id": "PARADISE-ABC123"}
                    )
                ],
                model="fake",
            ),
        ]
    )
    monkeypatch.setattr("app.api.v1.agents.get_ai_provider", lambda: fake)
    headers = await _auth_headers(client, unique_email)

    res = await client.post(
        "/api/v1/agents/run",
        json={"agent": "paradise_nepal_hotel_agent", "message": "Cancel booking PARADISE-ABC123"},
        headers=headers,
    )
    body = res.json()
    assert body["status"] == "awaiting_approval"
    assert body["approval_id"] is not None
