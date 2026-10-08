"""
End to end through the HTTP API: connect a site by URL, the generic
site_assistant answers from it (non-streaming and SSE streaming), and the
retrieved site excerpts reach the model but never pollute stored history.
"""
import asyncio
import json
import uuid

import pytest
from sqlalchemy import delete

from app.models.agent_installation import AgentInstallation
from app.models.memory import MemoryType
from app.services.ai.base import GenerationResult
from app.services.site_knowledge import service as site_service
from app.services.site_knowledge.crawler import Page
from tests.fakes import FakeAIProvider
from tests.test_site_knowledge import _keyword_embed

pytestmark = pytest.mark.asyncio

_PAGES = [
    Page("https://shop.example/hours", "Opening hours", "We are open Monday to Friday, hours 9am to 5pm."),
    Page("https://shop.example/refunds", "Refunds", "You can request a refund within 30 days."),
]


async def _auth_headers(client, email: str) -> dict:
    await client.post("/api/v1/auth/bootstrap", json={"email": email, "password": "pw123456"})
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "pw123456"})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _user_turn(fake: FakeAIProvider, call: int = 0) -> str:
    """The user message the model saw on a given call. (FakeAIProvider keeps a
    reference to the live message list, so [-1] would be the later reply.)"""
    return [m for m in fake.received_messages[call] if m.role == "user"][-1].content


def _patch(monkeypatch, fake: FakeAIProvider, pages=_PAGES):
    async def fake_crawl(url, *, max_pages, render_js):
        return pages

    monkeypatch.setattr("app.services.agent_execution.get_ai_provider", lambda: fake)
    monkeypatch.setattr("app.api.v1.sites.get_ai_provider", lambda: fake)
    monkeypatch.setattr(site_service, "crawl_site", fake_crawl)


async def _connect(client, headers, **extra) -> dict:
    res = await client.post(
        "/api/v1/sites", json={"url": "https://shop.example", **extra}, headers=headers
    )
    assert res.status_code == 202, res.text
    body = res.json()
    # wait for the background ingest to finish
    await asyncio.gather(*site_service._background_tasks)
    return body


async def test_connect_site_indexes_in_background_and_is_listed(client, unique_email, monkeypatch):
    fake = FakeAIProvider([], embed_fn=_keyword_embed)
    _patch(monkeypatch, fake)
    headers = await _auth_headers(client, unique_email)

    created = await _connect(client, headers)
    assert created["status"] == "pending"  # returned before the crawl finished
    assert created["api_key"] is None

    fetched = await client.get(f"/api/v1/sites/{created['id']}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "ready"
    assert fetched.json()["chunks_count"] == 2

    listing = await client.get("/api/v1/sites", headers=headers)
    assert [s["id"] for s in listing.json()] == [created["id"]]


async def test_sites_endpoints_require_auth(client):
    assert (await client.get("/api/v1/sites")).status_code == 401
    assert (await client.post("/api/v1/sites", json={"url": "https://x.example"})).status_code == 401


async def test_connect_site_rejects_non_http_url(client, unique_email):
    headers = await _auth_headers(client, unique_email)
    res = await client.post("/api/v1/sites", json={"url": "ftp://x.example"}, headers=headers)
    assert res.status_code == 422


async def test_delete_site_removes_its_knowledge(client, unique_email, monkeypatch, db_session):
    fake = FakeAIProvider([], embed_fn=_keyword_embed)
    _patch(monkeypatch, fake)
    headers = await _auth_headers(client, unique_email)
    created = await _connect(client, headers)

    res = await client.delete(f"/api/v1/sites/{created['id']}", headers=headers)
    assert res.status_code == 204
    assert (await client.get(f"/api/v1/sites/{created['id']}", headers=headers)).status_code == 404

    mem = await client.get("/api/v1/memory", params={"memory_type": MemoryType.KNOWLEDGE.value}, headers=headers)
    assert mem.json() == []


async def test_one_call_connect_issues_widget_key_that_answers_from_the_site(
    client, unique_email, monkeypatch
):
    fake = FakeAIProvider(
        [GenerationResult(content="We're open Monday to Friday, 9am to 5pm.", model="fake")],
        embed_fn=_keyword_embed,
    )
    _patch(monkeypatch, fake)
    headers = await _auth_headers(client, unique_email)

    created = await _connect(client, headers, create_widget_key=True)
    assert created["agent_slug"] == "site_assistant"
    assert created["api_key"].startswith("pak_")

    res = await client.post(
        "/api/v1/public/chat",
        json={"message": "What are your opening hours?"},
        headers={"X-API-Key": created["api_key"]},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["final_response"] == "We're open Monday to Friday, 9am to 5pm."
    assert body["iterations"] == 1  # one model call: retrieval happened in code

    # The model was handed the relevant excerpt, and only that one...
    sent_user_turn = _user_turn(fake)
    assert "Monday to Friday" in sent_user_turn
    assert "refund within 30 days" not in sent_user_turn
    assert "Customer message: What are your opening hours?" in sent_user_turn
    # ...with no tools offered (so it can't spend a round-trip deciding to search).
    # (FakeAIProvider doesn't record tools; assert via the agent definition instead.)
    from app.agents.registry import get_agent

    assert get_agent("site_assistant").allowed_tools == []


async def test_widget_key_works_for_an_older_account_without_the_site_agent_installed(
    client, unique_email, monkeypatch, db_session
):
    """An account created before site_assistant existed has no install row for
    it. Connecting a site with a key must install it, or the key 404s on the
    first chat (seen live on the dashboard's own long-standing account)."""
    fake = FakeAIProvider([GenerationResult(content="Open weekdays.", model="fake")], embed_fn=_keyword_embed)
    _patch(monkeypatch, fake)
    headers = await _auth_headers(client, unique_email)
    tenant_id = uuid.UUID((await client.get("/api/v1/auth/me", headers=headers)).json()["tenant_id"])

    # Simulate an older account: it has install rows, but none for site_assistant.
    await db_session.execute(delete(AgentInstallation).where(AgentInstallation.tenant_id == tenant_id))
    db_session.add(
        AgentInstallation(
            tenant_id=tenant_id, agent_slug="general_assistant", version_installed="1.0.0", is_enabled=True
        )
    )
    await db_session.commit()

    created = await _connect(client, headers, create_widget_key=True)
    res = await client.post(
        "/api/v1/public/chat", json={"message": "opening hours?"}, headers={"X-API-Key": created["api_key"]}
    )

    assert res.status_code == 200, res.text
    assert res.json()["agent"] == "site_assistant"


async def test_site_excerpts_are_not_persisted_into_conversation_history(
    client, unique_email, monkeypatch
):
    fake = FakeAIProvider(
        [GenerationResult(content="Open weekdays.", model="fake")], embed_fn=_keyword_embed
    )
    _patch(monkeypatch, fake)
    headers = await _auth_headers(client, unique_email)
    created = await _connect(client, headers, create_widget_key=True)
    key = {"X-API-Key": created["api_key"]}

    first = await client.post("/api/v1/public/chat", json={"message": "opening hours?"}, headers=key)
    conv = first.json()["conversation_id"]
    await client.post(
        "/api/v1/public/chat",
        json={"message": "and refund policy?", "conversation_id": conv},
        headers=key,
    )

    # On the second turn the replayed history holds the ORIGINAL first
    # question, not the first turn's retrieved excerpts.
    second_call = fake.received_messages[1]
    history_user_turns = [m.content for m in second_call if m.role == "user"]
    assert history_user_turns[0] == "opening hours?"
    assert "WEBSITE EXCERPTS" in history_user_turns[1]  # only the current turn carries excerpts


async def test_agent_without_the_flag_gets_no_site_content(client, unique_email, monkeypatch):
    fake = FakeAIProvider(
        [GenerationResult(content="hi", model="fake")], embed_fn=_keyword_embed
    )
    _patch(monkeypatch, fake)
    headers = await _auth_headers(client, unique_email)
    await _connect(client, headers)
    key_res = await client.post(
        "/api/v1/integrations/api-keys",
        json={"agent_slug": "general_assistant", "label": "w"},
        headers=headers,
    )

    await client.post(
        "/api/v1/public/chat",
        json={"message": "opening hours?"},
        headers={"X-API-Key": key_res.json()["api_key"]},
    )

    assert _user_turn(fake) == "opening hours?"


def _parse_sse(text: str) -> list[dict]:
    return [json.loads(line[len("data: "):]) for line in text.splitlines() if line.startswith("data: ")]


async def test_stream_endpoint_sends_start_tokens_and_done(client, unique_email, monkeypatch):
    fake = FakeAIProvider(
        [GenerationResult(content="Open weekdays 9 to 5.", model="fake")], embed_fn=_keyword_embed
    )
    _patch(monkeypatch, fake)
    headers = await _auth_headers(client, unique_email)
    created = await _connect(client, headers, create_widget_key=True)

    res = await client.post(
        "/api/v1/public/chat/stream",
        json={"message": "opening hours?"},
        headers={"X-API-Key": created["api_key"]},
    )

    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(res.text)
    assert events[0]["type"] == "start" and events[0]["conversation_id"]
    assert events[-1]["type"] == "done"
    assert events[-1]["data"]["final_response"] == "Open weekdays 9 to 5."
    assert events[-1]["data"]["conversation_id"] == events[0]["conversation_id"]
    streamed = "".join(e["text"] for e in events if e["type"] == "token")
    assert streamed == "Open weekdays 9 to 5."


async def test_stream_endpoint_auth_and_quota_errors_are_real_http_errors(client, unique_email):
    assert (await client.post("/api/v1/public/chat/stream", json={"message": "hi"})).status_code == 401
    bad = await client.post(
        "/api/v1/public/chat/stream", json={"message": "hi"}, headers={"X-API-Key": "pak_nope"}
    )
    assert bad.status_code == 401


async def test_stream_conversation_can_be_continued_with_non_stream_endpoint(
    client, unique_email, monkeypatch
):
    fake = FakeAIProvider(
        [GenerationResult(content="ok", model="fake")], embed_fn=_keyword_embed
    )
    _patch(monkeypatch, fake)
    headers = await _auth_headers(client, unique_email)
    created = await _connect(client, headers, create_widget_key=True)
    key = {"X-API-Key": created["api_key"]}

    streamed = await client.post("/api/v1/public/chat/stream", json={"message": "first"}, headers=key)
    conv = _parse_sse(streamed.text)[0]["conversation_id"]
    follow = await client.post(
        "/api/v1/public/chat", json={"message": "second", "conversation_id": conv}, headers=key
    )

    assert follow.status_code == 200
    roles_and_text = [(m.role, m.content) for m in fake.received_messages[1] if m.role in ("user", "assistant")]
    assert roles_and_text[0] == ("user", "first")
    assert roles_and_text[1] == ("assistant", "ok")
