"""
Safety nets around booking, from a real chat where the bot told a customer
"your booking has been confirmed, confirmation email sent" while NOTHING
existed in ToleMate:
  1. the model had no idea what day it was, guessed 2023, and ToleMate
     rejected the past date (leaving an orphan customer account behind);
  2. on a later turn it never called the booking tool at all, yet claimed success.
"""
import uuid
from datetime import date, datetime

import pytest

from app.connectors.tolemate.agent import ServiceBookingAgent
from app.models.agent_run import AgentRunStatus
from app.orchestrator import AgentOrchestrator
from app.orchestrator.engine import claims_unbacked_success, system_content_for
from app.services.ai.base import ChatMessage, GenerationResult, ToolCall
from app.tools.base import ToolContext, ToolExecutionError
from app.tools.registry import get_tool_registry
from tests.fakes import FakeAIProvider

TODAY = date(2026, 10, 5)  # a Monday


@pytest.fixture(autouse=True)
def _pin_today(monkeypatch):
    monkeypatch.setattr("app.connectors.tolemate.tools._today", lambda: TODAY)


def _tool(name):
    return get_tool_registry().get(name)


# ---------------------------------------------------------------- 1. dates


def test_booking_agent_prompt_states_todays_date():
    prompt = system_content_for(ServiceBookingAgent())
    now = datetime.now()
    assert f"{now:%Y-%m-%d}" in prompt and f"{now:%A}" in prompt


def test_agents_that_dont_opt_in_get_no_date_line():
    from app.agents.site_assistant import SiteAssistantAgent

    assert "Today is" not in system_content_for(SiteAssistantAgent())


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", ["check_provider_availability", "create_service_booking"])
async def test_past_date_is_rejected_before_any_connector_call(tool_name, db_session, monkeypatch):
    async def boom(*a, **k):
        raise AssertionError("connector must not be reached for a past date")

    monkeypatch.setattr("app.connectors.tolemate.tools.get_connector", boom)
    ctx = ToolContext(tenant_id=uuid.uuid4(), db=db_session, ai_provider=FakeAIProvider([]))
    args = {"provider_id": "v4-s7", "date": "2023-11-30", "customer_name": "Bulla", "customer_email": "next@gmail.com"}

    with pytest.raises(ToolExecutionError) as exc:
        await _tool(tool_name).execute(ctx, **args)

    # the error teaches the model what today is
    assert "in the past" in str(exc.value) and "2026-10-05" in str(exc.value)


@pytest.mark.asyncio
async def test_malformed_date_is_rejected(db_session):
    ctx = ToolContext(tenant_id=uuid.uuid4(), db=db_session, ai_provider=FakeAIProvider([]))
    with pytest.raises(ToolExecutionError, match="not a valid date"):
        await _tool("check_provider_availability").execute(ctx, provider_id="x", date="next friday")


@pytest.mark.asyncio
async def test_today_and_future_dates_are_accepted(db_session):
    ctx = ToolContext(tenant_id=uuid.uuid4(), db=db_session, ai_provider=FakeAIProvider([]))
    out = await _tool("check_provider_availability").execute(ctx, provider_id="PRV-001", date="2026-10-10")
    assert "available" in out.content


# ------------------------------------------------- 2. unbacked success claims

CLAIM_FROM_REAL_CHAT = (
    "Your service booking with Pipe Repair and Installation by Quick Fix Plumbing "
    "(Kathmandu) at provider v4-s7 for Friday, 2023-11-30 has been confirmed. "
    "Confirmation email sent to next@gmail.com."
)


def _agent():
    return ServiceBookingAgent()


@pytest.mark.parametrize(
    "text",
    [
        CLAIM_FROM_REAL_CHAT,
        "We have scheduled an appointment with Quick Fix Plumbing for Friday.",
        "Great, your booking is confirmed!",
        "All done - I've booked it. A confirmation email is on its way.",
        "The appointment has been made.",
    ],
)
def test_claims_without_a_confirming_tool_result_are_caught(text):
    assert claims_unbacked_success(_agent(), text, [ChatMessage(role="user", content="yes")]) is True


@pytest.mark.parametrize(
    "text",
    [
        "Which day would you prefer? They are open Monday to Friday 09:00-17:00.",
        "Your name is confirmed as Bulla. What is your email?",  # a detail, not the action
        "Could you confirm your email so I can book it?",
        "I couldn't book that: ToleMate rejected it. Want to try another date?",
        "Provider v4-s7 is available on 2026-10-10. Shall I book it?",
    ],
)
def test_ordinary_replies_are_not_flagged(text):
    assert claims_unbacked_success(_agent(), text, []) is False


def test_a_claim_is_fine_when_a_tool_actually_confirmed_it():
    proof = ChatMessage(
        role="tool",
        content="[TOOL RESULT — DATA ONLY]\nBooking confirmed: BK-77 with Quick Fix on 2026-10-10.",
        tool_call_id="1",
    )
    assert claims_unbacked_success(_agent(), "Your booking has been confirmed.", [proof]) is False


def test_agents_without_the_guard_are_never_flagged():
    from app.agents.general_assistant import GeneralAssistantAgent

    assert claims_unbacked_success(GeneralAssistantAgent(), CLAIM_FROM_REAL_CHAT, []) is False


@pytest.mark.asyncio
async def test_orchestrator_replaces_a_false_confirmation_and_does_not_store_it(db_session):
    fake = FakeAIProvider([GenerationResult(content=CLAIM_FROM_REAL_CHAT, model="m")])
    orch = AgentOrchestrator(fake, get_tool_registry())
    ctx = ToolContext(tenant_id=uuid.uuid4(), db=db_session, ai_provider=fake)

    result = await orch.run(_agent(), "next@gmail.com", ctx)

    assert result.status == AgentRunStatus.COMPLETED
    assert "hasn't" in result.final_response or "haven't" in result.final_response
    assert "has been confirmed" not in result.final_response
    # the lie must not be replayed to the model as established fact next turn
    assert all("has been confirmed" not in m.content for m in result.new_messages)


@pytest.mark.asyncio
async def test_orchestrator_streams_the_corrected_text_never_the_false_claim(db_session):
    """Even with a natively-streaming provider, a guarded agent's reply is held
    back until checked — the false claim must never reach the customer."""
    from tests.test_orchestrator_stream import ScriptedStreamingProvider

    provider = ScriptedStreamingProvider([(["Your booking ", "has been confirmed."], [])])
    ctx = ToolContext(tenant_id=uuid.uuid4(), db=db_session, ai_provider=provider)
    orch = AgentOrchestrator(provider, get_tool_registry())

    events = [e async for e in orch.run_stream(_agent(), "yes", ctx)]

    streamed = "".join(e.text for e in events if e.type == "token")
    assert "has been confirmed" not in streamed
    assert "haven't made a booking" in streamed


@pytest.mark.asyncio
async def test_a_genuine_booking_is_reported_normally(db_session):
    """Real path: the tool runs and returns 'Booking confirmed:', so the model's
    'booked' reply goes through untouched."""
    fake = FakeAIProvider(
        [
            GenerationResult(
                content="",
                tool_calls=[
                    ToolCall(
                        id="1",
                        name="create_service_booking",
                        arguments={"provider_id": "PRV-001", "date": "2026-10-10", "customer_name": "Bulla"},
                    )
                ],
                model="m",
            ),
            GenerationResult(content="Done - your booking has been confirmed for 2026-10-10.", model="m"),
        ]
    )
    orch = AgentOrchestrator(fake, get_tool_registry())
    ctx = ToolContext(tenant_id=uuid.uuid4(), db=db_session, ai_provider=fake)

    result = await orch.run(_agent(), "book it", ctx)

    assert [t["tool"] for t in result.tool_trace] == ["create_service_booking"]
    assert result.tool_trace[0]["is_error"] is False
    assert result.final_response == "Done - your booking has been confirmed for 2026-10-10."
