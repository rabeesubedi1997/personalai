"""
Routing between the heavy booking agent and the light site-question agent,
through the public chat API (the path Tolemate's widget uses).

Regression for a live failure: with website excerpts injected into the
booking agent, a small model answered from them and never called its tools —
it invented availability, swapped a cleaner for an electrician, and
garbled the customer's email.
"""
import pytest
from sqlalchemy import delete, update

from app.agents.registry import get_agent
from app.models.agent_installation import AgentInstallation
from app.services.ai.base import GenerationResult, ToolCall
from app.services.site_knowledge import service as site_service
from app.services.site_knowledge.crawler import Page
from tests.fakes import FakeAIProvider
from tests.test_site_knowledge import _keyword_embed

BOOKING = "tolemate_service_booking_agent"
INFO = "site_assistant"


async def _auth_headers(client, email: str) -> dict:
    await client.post("/api/v1/auth/bootstrap", json={"email": email, "password": "pw123456"})
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "pw123456"})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _setup(client, email, monkeypatch, responses):
    fake = FakeAIProvider(responses, embed_fn=_keyword_embed)

    async def fake_crawl(url, *, max_pages, render_js):
        return [Page("https://t.example/about", "About", "ToleMate has a 30-day guarantee on bookings.")]

    monkeypatch.setattr("app.services.agent_execution.get_ai_provider", lambda: fake)
    monkeypatch.setattr("app.api.v1.sites.get_ai_provider", lambda: fake)
    monkeypatch.setattr(site_service, "crawl_site", fake_crawl)

    headers = await _auth_headers(client, email)
    import asyncio

    await client.post("/api/v1/sites", json={"url": "https://t.example"}, headers=headers)
    await asyncio.gather(*site_service._background_tasks)
    key = (
        await client.post(
            "/api/v1/integrations/api-keys",
            json={"agent_slug": BOOKING, "label": "ToleMate widget"},
            headers=headers,
        )
    ).json()["api_key"]
    return fake, {"X-API-Key": key}


async def _chat(client, key, message, conversation_id=None):
    res = await client.post(
        "/api/v1/public/chat",
        json={"message": message, "conversation_id": conversation_id},
        headers=key,
    )
    assert res.status_code == 200, res.text
    return res.json()


@pytest.mark.asyncio
async def test_plain_question_goes_to_the_light_site_agent(client, unique_email, monkeypatch):
    _, key = await _setup(client, unique_email, monkeypatch, [GenerationResult(content="30 days.", model="m")])

    for question in ("What is ToleMate and how does it work?", "Is there a guarantee on the services?", "hello"):
        body = await _chat(client, key, question)
        assert body["agent"] == INFO, question


@pytest.mark.asyncio
async def test_booking_requests_go_to_the_booking_agent(client, unique_email, monkeypatch):
    _, key = await _setup(client, unique_email, monkeypatch, [GenerationResult(content="ok", model="m")])

    for message in ("i need cleaning services", "I want to book a plumber", "Do you have electricians available?", "cancel my booking"):
        body = await _chat(client, key, message)
        assert body["agent"] == BOOKING, message


@pytest.mark.asyncio
async def test_booking_conversation_stays_with_the_booking_agent(client, unique_email, monkeypatch):
    """The exact failing chat: after 'i need cleaning services', follow-ups
    like an email address or a bare 'yes' must stay with the tool agent."""
    _, key = await _setup(client, unique_email, monkeypatch, [GenerationResult(content="ok", model="m")])

    first = await _chat(client, key, "i need cleaning services")
    conv = first["conversation_id"]
    for follow_up in ("yes, and my email is rabi@hitechvalley.com.au", "yes", "tomorrow at 10", "thanks"):
        body = await _chat(client, key, follow_up, conv)
        assert body["agent"] == BOOKING, follow_up


@pytest.mark.asyncio
async def test_plain_question_in_the_middle_of_a_booking_goes_to_the_info_agent(
    client, unique_email, monkeypatch
):
    """Seen live: 'Is there a guarantee on the services?' mid-booking stayed
    with the booking agent, which has no site knowledge and said it didn't know."""
    _, key = await _setup(client, unique_email, monkeypatch, [GenerationResult(content="ok", model="m")])

    first = await _chat(client, key, "i need cleaning services")
    assert first["agent"] == BOOKING
    asked = await _chat(client, key, "Is there a guarantee on the services?", first["conversation_id"])
    assert asked["agent"] == INFO
    # A follow-up that sounds like a booking goes straight back to the booking agent.
    back = await _chat(client, key, "yes please book it", first["conversation_id"])
    assert back["agent"] == BOOKING


@pytest.mark.asyncio
async def test_routing_works_for_an_older_tenant_that_never_got_the_info_agent(
    client, unique_email, monkeypatch, db_session
):
    """Default agents are only pre-installed for brand-new tenants, so an
    account created before site_assistant existed has NO row for it. That must
    count as available, not as 'uninstalled' — the live failure was exactly
    this: routing silently fell back to the booking agent."""
    _, key = await _setup(client, unique_email, monkeypatch, [GenerationResult(content="ok", model="m")])
    await db_session.execute(delete(AgentInstallation).where(AgentInstallation.agent_slug == INFO))
    await db_session.commit()

    body = await _chat(client, key, "Is there a guarantee on the services?")

    assert body["agent"] == INFO


@pytest.mark.asyncio
async def test_routing_respects_a_tenant_that_explicitly_turned_the_info_agent_off(
    client, unique_email, monkeypatch, db_session
):
    _, key = await _setup(client, unique_email, monkeypatch, [GenerationResult(content="ok", model="m")])
    await db_session.execute(
        update(AgentInstallation).where(AgentInstallation.agent_slug == INFO).values(is_enabled=False)
    )
    await db_session.commit()

    body = await _chat(client, key, "Is there a guarantee on the services?")

    assert body["agent"] == BOOKING


@pytest.mark.asyncio
async def test_info_conversation_switches_to_booking_when_visitor_asks_to_book(client, unique_email, monkeypatch):
    _, key = await _setup(client, unique_email, monkeypatch, [GenerationResult(content="ok", model="m")])

    first = await _chat(client, key, "How does ToleMate work?")
    assert first["agent"] == INFO
    second = await _chat(client, key, "ok I want to book a plumber", first["conversation_id"])
    assert second["agent"] == BOOKING


@pytest.mark.asyncio
async def test_booking_agent_gets_no_website_excerpts_but_info_agent_does(client, unique_email, monkeypatch):
    fake, key = await _setup(client, unique_email, monkeypatch, [GenerationResult(content="ok", model="m")])

    def last_user(call):
        return [m for m in fake.received_messages[call] if m.role == "user"][-1].content

    await _chat(client, key, "Is there a guarantee on the services?")  # -> info
    await _chat(client, key, "i need a cleaner")  # -> booking
    assert "WEBSITE EXCERPTS" in last_user(0)
    assert "30-day guarantee" in last_user(0)
    assert last_user(1) == "i need a cleaner"


@pytest.mark.asyncio
async def test_booking_agent_can_call_its_tools_again(client, unique_email, monkeypatch):
    """With no excerpts to answer from, a booking request runs the tool loop."""
    _, key = await _setup(
        client,
        unique_email,
        monkeypatch,
        [
            GenerationResult(
                content="",
                tool_calls=[ToolCall(id="1", name="search_service_providers", arguments={"service_query": "cleaning", "location": "Kathmandu"})],
                model="m",
            ),
            GenerationResult(content="I found Sparkling Clean Services.", model="m"),
        ],
    )

    body = await _chat(client, key, "i need cleaning services")

    assert body["agent"] == BOOKING
    assert [t["tool"] for t in body["tool_trace"]] == ["search_service_providers"]
    assert body["iterations"] == 2


def test_tolemate_agent_is_wired_to_route_info_questions_to_site_agent():
    booking = get_agent(BOOKING)
    assert booking.info_agent_slug == INFO
    assert booking.uses_site_knowledge is False
    assert get_agent(INFO).allowed_tools == []
