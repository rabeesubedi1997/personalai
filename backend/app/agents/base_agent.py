"""
Agent base class (spec Section 9). Every agent declares its identity,
system prompt, and — critically — an explicit `allowed_tools` list. There
is no "give this agent every tool" shortcut; an agent that needs a new
capability gets it added to its own allow-list, deliberately.
"""
from __future__ import annotations

from abc import ABC

from app.agents.flow import ConversationFlow


class BaseAgent(ABC):
    name: str
    description: str
    system_prompt: str
    allowed_tools: list[str] = []
    # Phase 12 (Agent Marketplace): catalog metadata. Bump `version` when an
    # agent's behavior changes meaningfully (prompt, tool list) — installed
    # tenants keep running their installed version's metadata until they
    # reinstall, same convention as any package marketplace.
    version: str = "1.0.0"
    category: str = "general"
    # Opt in to having excerpts of the tenant's connected website(s)
    # retrieved and placed next to each customer message (see
    # app/services/site_knowledge). Off by default so existing agents'
    # prompts are unchanged.
    uses_site_knowledge: bool = False
    # An agent that does actions with tools (booking) is slow and, handed
    # website excerpts, a small model starts answering from them instead of
    # calling its tools. So such an agent can name a lighter agent that
    # handles plain questions about the site; see app/services/agent_router.py.
    info_agent_slug: str | None = None
    # Tell the agent today's date in its system prompt. A model has no clock:
    # asked to book "Friday" it guessed 2023, and the business rejected a date
    # in the past. Opt-in so other agents' prompts (and prompt caches) are
    # untouched; the date changes once a day.
    # A code-driven flow that takes over this agent's conversations (see
    # app/agents/flow.py) for jobs a small model can't be trusted to do itself.
    flow: ConversationFlow | None = None
    needs_current_date: bool = False
    # Guard against a model CLAIMING an action it never did. If the final reply
    # matches `success_claim_pattern` ("your booking has been confirmed") but no
    # tool result containing `success_proof_marker` ("Booking confirmed:")
    # exists in the conversation, the reply is replaced with an honest one.
    # The prompt already says "never claim success unless the tool confirmed
    # it"; a 3B model ignored that and told a customer a booking existed when
    # the tool was never even called, so this is enforced in code.
    success_claim_pattern: str | None = None
    success_proof_marker: str | None = None
    success_claim_correction: str = (
        "I haven't actually completed that yet, so nothing is confirmed. "
        "Tell me what you'd like and I'll do it properly."
    )
