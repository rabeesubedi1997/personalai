"""
Pick which agent actually handles a message, for an agent that has a lighter
"info" sibling (see BaseAgent.info_agent_slug).

Why: an action agent (booking) carries a big prompt plus tools — slow on a CPU
model, and it can't stream. Most visitor messages are just questions about the
site ("how does it work?", "is there a guarantee?"), which the tool-less site
agent answers in one fast call. But when the visitor wants something DONE, it
must reach the action agent, and stay there for the rest of that conversation.

The rule is deliberately biased toward the action agent: wrongly sending a
plain question to it just costs speed, while wrongly sending a booking request
to the info agent would silently fail to book. So: info agent only when the
message has no booking-ish words AND the conversation isn't already with the
action agent.
"""
from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base_agent import BaseAgent
from app.agents.registry import get_agent
from app.models.agent_run import AgentRun
from app.services.marketplace import get_installation

_ACTION_INTENT = re.compile(
    r"\b("
    r"book\w*|appointment\w*|schedul\w*|reserv\w*|cancel\w*|reschedul\w*|"
    r"availab\w*|hire|need\w*|want\w*|looking|find|get me|order\w*|"
    r"plumb\w*|electric\w*|clean\w*|paint\w*|garden\w*|carpent\w*|mover\w*|moving|"
    r"repair\w*|fix\w*|install\w*|handyman|maid|"
    r"my name|my email|email is|"
    r"yes|yeah|yep|ok|okay|sure|confirm\w*|proceed|go ahead|please do"
    r")\b",
    re.IGNORECASE,
)


_QUESTION = re.compile(
    r"\?\s*$|^\s*(what|whats|how|why|when|where|who|which|is|are|do|does|did|can|could|will|would)\b",
    re.IGNORECASE,
)


async def route_agent(
    db: AsyncSession,
    agent: BaseAgent,
    *,
    tenant_id: uuid.UUID,
    message: str,
    conversation_id: uuid.UUID | None,
) -> BaseAgent:
    """The agent that should answer `message`: `agent` itself, or its info
    sibling for a plain question."""
    if not agent.info_agent_slug:
        return agent
    info_agent = get_agent(agent.info_agent_slug)
    if info_agent is None:
        return agent
    # Available unless the tenant explicitly turned it off. "No installation
    # row" is NOT "off": default agents are only pre-installed for brand-new
    # tenants, so an older tenant simply never got a newer helper agent —
    # treating that as "uninstalled" silently disabled routing for them.
    installation = await get_installation(db, tenant_id, info_agent.name)
    if installation is not None and not installation.is_enabled:
        return agent
    if _ACTION_INTENT.search(message):
        return agent

    # A plain question ("is there a guarantee?") goes to the info agent even
    # in the middle of a booking — the booking agent has no site knowledge
    # and would say it doesn't know. Anything that isn't a question
    # ("tomorrow at 10", "thanks") stays with the agent already helping.
    if conversation_id is not None and not _QUESTION.search(message):
        last_agent = (
            await db.execute(
                select(AgentRun.agent_name)
                .where(
                    AgentRun.tenant_id == tenant_id,
                    AgentRun.conversation_id == conversation_id,
                )
                .order_by(AgentRun.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if last_agent == agent.name:
            return agent  # mid-booking: keep the thread with the agent that has the tools
    return info_agent
