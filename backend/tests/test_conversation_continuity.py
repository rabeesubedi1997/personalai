"""
Fix for the gap found live-testing Phase 6: each POST /api/v1/agents/run
call used to start a fresh context with no memory of prior turns. These
tests prove a conversation_id now actually carries history forward.
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


async def test_first_call_without_conversation_id_returns_a_new_one(
    client, unique_email, monkeypatch
):
    fake = FakeAIProvider([GenerationResult(content="Hi there!", model="fake")])
    monkeypatch.setattr("app.api.v1.agents.get_ai_provider", lambda: fake)
    headers = await _auth_headers(client, unique_email)

    res = await client.post(
        "/api/v1/agents/run",
        json={"agent": "general_assistant", "message": "hi"},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["conversation_id"] is not None


async def test_continuing_a_conversation_replays_prior_turns_to_the_model(
    client, unique_email, monkeypatch
):
    fake = FakeAIProvider(
        [
            GenerationResult(content="I found an electrician: Bikash Electrical.", model="fake"),
            GenerationResult(content="Sure, I'll book Bikash Electrical for you.", model="fake"),
        ]
    )
    monkeypatch.setattr("app.api.v1.agents.get_ai_provider", lambda: fake)
    headers = await _auth_headers(client, unique_email)

    first = await client.post(
        "/api/v1/agents/run",
        json={"agent": "general_assistant", "message": "Find me an electrician"},
        headers=headers,
    )
    conversation_id = first.json()["conversation_id"]
    assert conversation_id is not None

    second = await client.post(
        "/api/v1/agents/run",
        json={
            "agent": "general_assistant",
            "message": "Yes, book that one",
            "conversation_id": conversation_id,
        },
        headers=headers,
    )
    assert second.status_code == 200
    assert second.json()["conversation_id"] == conversation_id

    # The second call to the model must have included the first turn's
    # exchange — this is the actual fix being verified, not just that the
    # API accepted a conversation_id.
    second_call_messages = fake.received_messages[1]
    contents = [m.content for m in second_call_messages]
    assert any("Find me an electrician" in c for c in contents)
    assert any("Bikash Electrical" in c for c in contents)
    assert any("Yes, book that one" in c for c in contents)


async def test_conversation_history_persists_across_separate_requests(
    client, unique_email, monkeypatch
):
    # Three separate HTTP calls, same conversation — each should only need
    # to add its own new turn, with full history available each time.
    fake = FakeAIProvider(
        [
            GenerationResult(content="What service do you need?", model="fake"),
            GenerationResult(content="Got it, electrician. What city?", model="fake"),
            GenerationResult(content="Searching in Lalitpur now.", model="fake"),
        ]
    )
    monkeypatch.setattr("app.api.v1.agents.get_ai_provider", lambda: fake)
    headers = await _auth_headers(client, unique_email)

    r1 = await client.post(
        "/api/v1/agents/run",
        json={"agent": "general_assistant", "message": "I need a service booked"},
        headers=headers,
    )
    cid = r1.json()["conversation_id"]

    await client.post(
        "/api/v1/agents/run",
        json={"agent": "general_assistant", "message": "An electrician", "conversation_id": cid},
        headers=headers,
    )
    await client.post(
        "/api/v1/agents/run",
        json={"agent": "general_assistant", "message": "Lalitpur", "conversation_id": cid},
        headers=headers,
    )

    third_call_messages = fake.received_messages[2]
    contents = " ".join(m.content for m in third_call_messages)
    assert "I need a service booked" in contents
    assert "An electrician" in contents
    assert "Lalitpur" in contents


async def test_continuing_another_tenants_conversation_id_starts_fresh_not_leaked(
    client, unique_email, monkeypatch
):
    # Safety property: tenant isolation holds even for conversation replay.
    # Tenant B guessing/reusing tenant A's conversation_id must NOT see
    # tenant A's history — ConversationStore filters by tenant_id, so it
    # silently behaves as a fresh thread rather than leaking data.
    fake = FakeAIProvider(
        [
            GenerationResult(content="Tenant A's secret plan details here.", model="fake"),
            GenerationResult(content="Hello, how can I help?", model="fake"),
        ]
    )
    monkeypatch.setattr("app.api.v1.agents.get_ai_provider", lambda: fake)

    tenant_a_headers = await _auth_headers(client, unique_email)
    tenant_b_headers = await _auth_headers(client, f"b-{unique_email}")

    r1 = await client.post(
        "/api/v1/agents/run",
        json={"agent": "general_assistant", "message": "Tell me the secret plan"},
        headers=tenant_a_headers,
    )
    conversation_id = r1.json()["conversation_id"]

    await client.post(
        "/api/v1/agents/run",
        json={
            "agent": "general_assistant",
            "message": "hi",
            "conversation_id": conversation_id,
        },
        headers=tenant_b_headers,
    )

    second_call_messages = fake.received_messages[1]
    contents = " ".join(m.content for m in second_call_messages)
    assert "secret plan" not in contents.lower()


async def test_awaiting_approval_turn_is_still_replayable_afterward(
    client, unique_email, monkeypatch
):
    # Regression check for the dangling-tool-call fix: a turn that paused
    # for approval must still produce a valid, replayable conversation —
    # no unresolved tool_calls with no matching tool response.
    fake = FakeAIProvider(
        [
            GenerationResult(
                content="",
                tool_calls=[
                    ToolCall(id="1", name="cancel_booking", arguments={"booking_id": "BK-1"})
                ],
                model="fake",
            ),
            GenerationResult(content="Understood, still pending.", model="fake"),
        ]
    )
    monkeypatch.setattr("app.api.v1.agents.get_ai_provider", lambda: fake)
    headers = await _auth_headers(client, unique_email)

    first = await client.post(
        "/api/v1/agents/run",
        json={"agent": "general_assistant", "message": "cancel booking BK-1"},
        headers=headers,
    )
    conversation_id = first.json()["conversation_id"]
    assert first.json()["status"] == "awaiting_approval"

    # Continuing the conversation must not error (e.g. on a malformed
    # dangling tool_calls message) — this is what would break if the
    # orchestrator didn't close out the pending tool_call.
    second = await client.post(
        "/api/v1/agents/run",
        json={
            "agent": "general_assistant",
            "message": "any update?",
            "conversation_id": conversation_id,
        },
        headers=headers,
    )
    assert second.status_code == 200
    second_messages = fake.received_messages[1]
    tool_msgs = [m for m in second_messages if m.role == "tool"]
    assert any("pending" in m.content.lower() for m in tool_msgs)
