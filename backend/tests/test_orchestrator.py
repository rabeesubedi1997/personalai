import uuid

import pytest

from app.agents.general_assistant import GeneralAssistantAgent
from app.core.config import settings
from app.models.agent_run import AgentRunStatus
from app.orchestrator import AgentOrchestrator
from app.services.ai.base import GenerationResult, ToolCall
from app.tools.base import ToolContext
from app.tools.registry import get_tool_registry
from tests.fakes import FakeAIProvider

pytestmark = pytest.mark.asyncio


@pytest.fixture
def context(db_session):
    return ToolContext(
        tenant_id=uuid.uuid4(), db=db_session, ai_provider=FakeAIProvider(responses=[])
    )


async def test_completes_without_any_tool_calls(context):
    provider = FakeAIProvider([GenerationResult(content="Hello there!", model="fake")])
    orchestrator = AgentOrchestrator(provider, get_tool_registry())
    result = await orchestrator.run(GeneralAssistantAgent(), "hi", context)

    assert result.status == AgentRunStatus.COMPLETED
    assert result.final_response == "Hello there!"
    assert result.iterations == 1
    assert result.tool_trace == []


async def test_executes_allowed_tool_then_completes(context):
    provider = FakeAIProvider(
        [
            GenerationResult(
                content="",
                tool_calls=[ToolCall(id="1", name="get_current_time", arguments={})],
                model="fake",
            ),
            GenerationResult(content="It is currently ... (used the tool)", model="fake"),
        ]
    )
    orchestrator = AgentOrchestrator(provider, get_tool_registry())
    result = await orchestrator.run(GeneralAssistantAgent(), "what time is it?", context)

    assert result.status == AgentRunStatus.COMPLETED
    assert result.iterations == 2
    assert len(result.tool_trace) == 1
    assert result.tool_trace[0]["tool"] == "get_current_time"
    assert result.tool_trace[0]["is_error"] is False


async def test_unauthorized_tool_call_is_denied_not_executed(context):
    # "delete_everything" is not in GeneralAssistantAgent.allowed_tools and
    # isn't even registered — the orchestrator must refuse it, not crash,
    # and must not silently pretend it ran successfully.
    provider = FakeAIProvider(
        [
            GenerationResult(
                content="",
                tool_calls=[ToolCall(id="1", name="delete_everything", arguments={})],
                model="fake",
            ),
            GenerationResult(content="I could not do that.", model="fake"),
        ]
    )
    orchestrator = AgentOrchestrator(provider, get_tool_registry())
    result = await orchestrator.run(GeneralAssistantAgent(), "delete everything", context)

    assert result.tool_trace[0]["tool"] == "delete_everything"
    assert result.tool_trace[0]["is_error"] is True
    assert result.status == AgentRunStatus.COMPLETED


async def test_stops_at_max_iterations_never_loops_forever(context):
    # Provider always asks for another tool call — orchestrator must cut
    # this off at AGENT_MAX_ITERATIONS rather than looping indefinitely.
    endless_tool_call = GenerationResult(
        content="",
        tool_calls=[ToolCall(id="x", name="get_current_time", arguments={})],
        model="fake",
    )
    provider = FakeAIProvider([endless_tool_call])
    orchestrator = AgentOrchestrator(provider, get_tool_registry())
    result = await orchestrator.run(GeneralAssistantAgent(), "loop forever please", context)

    assert result.status == AgentRunStatus.MAX_ITERATIONS_REACHED
    assert result.iterations == settings.agent_max_iterations


async def test_stops_at_max_tool_calls_limit(context):
    # A single turn that requests more tool calls than AGENT_MAX_TOOL_CALLS
    # allows must be escalated, not executed past the limit.
    many_calls = [
        ToolCall(id=str(i), name="get_current_time", arguments={})
        for i in range(settings.agent_max_tool_calls + 5)
    ]
    provider = FakeAIProvider(
        [GenerationResult(content="", tool_calls=many_calls, model="fake")]
    )
    orchestrator = AgentOrchestrator(provider, get_tool_registry())
    result = await orchestrator.run(GeneralAssistantAgent(), "call many tools", context)

    assert result.status == AgentRunStatus.ESCALATED
    assert len(result.tool_trace) == settings.agent_max_tool_calls
