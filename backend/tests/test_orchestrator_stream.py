"""
Streaming behaviour of the orchestrator: what a visitor would see arrive,
and in what order, for providers that stream natively vs. those that don't.
"""
import uuid
from collections.abc import AsyncIterator

import pytest

from app.agents.base_agent import BaseAgent
from app.models.agent_run import AgentRunStatus
from app.orchestrator import AgentOrchestrator
from app.services.ai.base import (
    AIProvider,
    ChatMessage,
    GenerationResult,
    StreamChunk,
    ToolCall,
    ToolSpec,
)
from app.tools.base import ToolContext
from app.tools.registry import get_tool_registry
from tests.fakes import FakeAIProvider

pytestmark = pytest.mark.asyncio


class _Agent(BaseAgent):
    name = "stream_test_agent"
    description = "x"
    system_prompt = "Be brief."
    allowed_tools = ["get_current_time"]


class ScriptedStreamingProvider(AIProvider):
    """A provider that streams natively: each scripted turn is a list of
    text pieces plus optional tool calls on the final chunk."""

    streams_natively = True

    def __init__(self, turns: list[tuple[list[str], list[ToolCall]]]):
        self.turns = turns
        self.i = 0
        self.seen: list[list[ChatMessage]] = []

    async def stream_with_tools(
        self, messages: list[ChatMessage], tools: list[ToolSpec]
    ) -> AsyncIterator[StreamChunk]:
        self.seen.append(list(messages))
        pieces, calls = self.turns[min(self.i, len(self.turns) - 1)]
        self.i += 1
        for piece in pieces:
            yield StreamChunk(text=piece)
        yield StreamChunk(final=GenerationResult(content="".join(pieces), tool_calls=calls, model="m"))

    async def generate(self, prompt, *, system=None):  # pragma: no cover - unused
        raise NotImplementedError

    async def chat(self, messages):  # pragma: no cover - unused
        raise NotImplementedError

    async def generate_with_tools(self, messages, tools):  # pragma: no cover - unused
        raise NotImplementedError

    async def health_check(self):  # pragma: no cover - unused
        return True

    async def embed(self, text):  # pragma: no cover - unused
        return [1.0]


async def _collect(orchestrator, agent, message, db_session, **kw):
    ctx = ToolContext(tenant_id=uuid.uuid4(), db=db_session, ai_provider=orchestrator.ai_provider)
    return [e async for e in orchestrator.run_stream(agent, message, ctx, **kw)]


async def test_native_streaming_yields_tokens_in_order_then_done(db_session):
    provider = ScriptedStreamingProvider([(["Hel", "lo ", "there"], [])])
    events = await _collect(AgentOrchestrator(provider, get_tool_registry()), _Agent(), "hi", db_session)

    assert [e.type for e in events] == ["token", "token", "token", "done"]
    assert "".join(e.text for e in events if e.type == "token") == "Hello there"
    assert events[-1].result.final_response == "Hello there"
    assert events[-1].result.status == AgentRunStatus.COMPLETED


async def test_non_streaming_provider_emits_the_whole_reply_as_one_token(db_session):
    fake = FakeAIProvider([GenerationResult(content="All at once.", model="m")])
    events = await _collect(AgentOrchestrator(fake, get_tool_registry()), _Agent(), "hi", db_session)

    assert [e.type for e in events] == ["token", "done"]
    assert events[0].text == "All at once."


async def test_tool_turn_emits_tool_event_and_separates_text_segments(db_session):
    provider = ScriptedStreamingProvider(
        [
            (["Let me check."], [ToolCall(id="1", name="get_current_time", arguments={})]),
            (["It is noon."], []),
        ]
    )
    events = await _collect(AgentOrchestrator(provider, get_tool_registry()), _Agent(), "time?", db_session)

    assert [e.type for e in events] == ["token", "tool", "token", "token", "done"]
    assert events[1].text == "get_current_time"
    # a blank line separates the pre-tool text from the post-tool answer
    assert events[2].text == "\n\n"
    assert events[-1].result.final_response == "It is noon."
    assert events[-1].result.tool_call_count == 1


async def test_half_formed_tool_call_text_is_never_streamed_to_the_visitor(db_session):
    provider = ScriptedStreamingProvider(
        [
            (["Sure, ", "<tool_call>", '{"name": "x"'], []),  # broken: text, not a real call
            (["Here is the real answer."], []),
        ]
    )
    events = await _collect(AgentOrchestrator(provider, get_tool_registry()), _Agent(), "hi", db_session)

    streamed = "".join(e.text for e in events if e.type == "token")
    assert "<tool_call>" not in streamed
    assert streamed.endswith("Here is the real answer.")
    assert events[-1].result.final_response == "Here is the real answer."


async def test_run_and_run_stream_agree(db_session):
    def make():
        return FakeAIProvider([GenerationResult(content="Same answer.", model="m")])

    a = await AgentOrchestrator(make(), get_tool_registry()).run(
        _Agent(), "hi", ToolContext(tenant_id=uuid.uuid4(), db=db_session, ai_provider=make())
    )
    events = await _collect(AgentOrchestrator(make(), get_tool_registry()), _Agent(), "hi", db_session)
    b = events[-1].result

    assert (a.status, a.final_response, a.iterations) == (b.status, b.final_response, b.iterations)


async def test_reference_context_is_shown_to_model_but_not_persisted(db_session):
    provider = ScriptedStreamingProvider([(["ok"], [])])
    events = await _collect(
        AgentOrchestrator(provider, get_tool_registry()),
        _Agent(),
        "what are your hours?",
        db_session,
        reference_context="WEBSITE EXCERPTS: open 9-5",
    )

    sent = provider.seen[0][-1].content
    assert sent.startswith("WEBSITE EXCERPTS: open 9-5")
    assert sent.endswith("Customer message: what are your hours?")

    persisted = events[-1].result.new_messages
    assert persisted[0].role == "user" and persisted[0].content == "what are your hours?"
    assert all("WEBSITE EXCERPTS" not in m.content for m in persisted)
