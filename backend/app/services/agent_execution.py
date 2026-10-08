"""
Shared agent-run execution path, used by BOTH the internal (JWT-authenticated
dashboard user) `POST /api/v1/agents/run` and the public (API-key-authenticated
external widget) `POST /api/v1/public/chat` and `/public/chat/stream`. Extracted
so the entry points can never drift apart on billing enforcement, install
checks, conversation handling, or approval/notification wiring — one
implementation, callers with different auth in front of it.

A run is three steps: prepare (checks + conversation thread), run the
orchestrator, finalize (persist + approvals + notifications). The streaming
endpoint needs prepare to happen BEFORE it starts streaming, so it can still
return a proper HTTP error (404/402) instead of a 200 stream that fails.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base_agent import BaseAgent
from app.agents.registry import get_agent
from app.core.logging import get_logger
from app.db.session import async_session_factory
from app.models.agent_run import AgentRun, AgentRunStatus
from app.models.approval import Approval
from app.models.notification import NotificationChannel
from app.orchestrator import AgentOrchestrator
from app.orchestrator.engine import OrchestratorResult
from app.schemas.agents import AgentRunResponse
from app.services.ai.base import AIProvider, ChatMessage
from app.services.ai.factory import get_ai_provider
from app.services.agent_router import route_agent
from app.services.billing import check_usage_allowed
from app.services.conversation_store import ConversationStore
from app.services.marketplace import ensure_default_agents_installed, is_installed
from app.services.notifications.service import NotificationService
from app.services.site_knowledge import build_site_context
from app.tools.base import ToolContext
from app.tools.registry import get_tool_registry

logger = get_logger(__name__)


@dataclass
class PreparedRun:
    """Everything decided before the model is called: the run is allowed
    (agent exists + installed, plan has quota) and the conversation thread
    is resolved."""

    agent: BaseAgent
    tenant_id: uuid.UUID
    acting_user_id: uuid.UUID
    message: str
    conversation_id: uuid.UUID
    history: list[ChatMessage]


async def prepare_agent_run(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    acting_user_id: uuid.UUID,
    agent_slug: str,
    message: str,
    conversation_id: uuid.UUID | None,
) -> PreparedRun:
    agent = get_agent(agent_slug)
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown agent '{agent_slug}'"
        )

    await ensure_default_agents_installed(db, tenant_id)
    if not await is_installed(db, tenant_id, agent.name):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Agent '{agent.name}' is not installed for this tenant. "
                "Install it via POST /api/v1/marketplace/agents/{slug}/install first."
            ),
        )

    # The key/requested agent decides what's allowed; the router may hand a
    # plain question to its lighter sibling (see app/services/agent_router.py).
    agent = await route_agent(
        db, agent, tenant_id=tenant_id, message=message, conversation_id=conversation_id
    )

    allowed, plan, usage = await check_usage_allowed(db, tenant_id)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"Monthly agent run limit reached for the '{plan.name}' plan "
                f"({usage}/{plan.max_agent_runs_per_month}). Upgrade your plan to continue."
            ),
        )

    resolved_conversation_id = conversation_id or uuid.uuid4()
    history = (
        await ConversationStore(db).load(
            tenant_id=tenant_id, conversation_id=resolved_conversation_id
        )
        if conversation_id is not None
        else []
    )
    return PreparedRun(
        agent=agent,
        tenant_id=tenant_id,
        acting_user_id=acting_user_id,
        message=message,
        conversation_id=resolved_conversation_id,
        history=history,
    )


async def _reference_context(
    db: AsyncSession, ai_provider: AIProvider, prepared: PreparedRun
) -> str | None:
    """Website excerpts relevant to this message, for agents that opted in.
    Knowledge lookup is an enhancement, never a reason to fail the chat: if
    embedding is down the agent still answers, just without site content."""
    if not prepared.agent.uses_site_knowledge:
        return None
    try:
        return await build_site_context(db, ai_provider, prepared.tenant_id, prepared.message)
    except Exception as exc:  # noqa: BLE001 - see docstring
        logger.warning("site_context_failed", error=str(exc))
        return None


async def finalize_agent_run(
    db: AsyncSession, prepared: PreparedRun, result: OrchestratorResult
) -> AgentRunResponse:
    """Persist the conversation + AgentRun, and raise the approval and
    notification if the run paused for one."""
    agent = prepared.agent
    tenant_id = prepared.tenant_id

    await ConversationStore(db).append(
        tenant_id=tenant_id,
        conversation_id=prepared.conversation_id,
        messages=result.new_messages,
    )

    run = AgentRun(
        tenant_id=tenant_id,
        user_id=prepared.acting_user_id,
        conversation_id=prepared.conversation_id,
        agent_name=agent.name,
        model=result.model,
        request_text=prepared.message,
        final_response=result.final_response,
        status=result.status,
        iterations=result.iterations,
        tool_call_count=result.tool_call_count,
        tool_trace=result.tool_trace,
        error=result.error,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    approval_id = None
    if result.status == AgentRunStatus.AWAITING_APPROVAL and result.pending_approval:
        approval = Approval(
            tenant_id=tenant_id,
            agent_run_id=run.id,
            agent_name=agent.name,
            tool_name=result.pending_approval["tool"],
            arguments=result.pending_approval["arguments"],
            allowed_tool_names=agent.allowed_tools,
        )
        db.add(approval)
        await db.commit()
        await db.refresh(approval)
        approval_id = approval.id

        await NotificationService(db).send(
            tenant_id=tenant_id,
            user_id=prepared.acting_user_id,
            channel=NotificationChannel.WEB,
            subject="Action pending approval",
            message=(
                f"Your request to use '{approval.tool_name}' via {agent.name} is "
                "pending human approval."
            ),
            metadata={"approval_id": str(approval.id), "agent_run_id": str(run.id)},
        )

    return AgentRunResponse(
        run_id=run.id,
        agent=agent.name,
        status=result.status,
        final_response=result.final_response,
        iterations=result.iterations,
        tool_trace=result.tool_trace,
        model=result.model,
        error=result.error,
        approval_id=approval_id,
        conversation_id=prepared.conversation_id,
    )


async def execute_agent_run(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    acting_user_id: uuid.UUID,
    agent_slug: str,
    message: str,
    conversation_id: uuid.UUID | None,
) -> AgentRunResponse:
    prepared = await prepare_agent_run(
        db,
        tenant_id=tenant_id,
        acting_user_id=acting_user_id,
        agent_slug=agent_slug,
        message=message,
        conversation_id=conversation_id,
    )
    ai_provider = get_ai_provider()
    orchestrator = AgentOrchestrator(ai_provider, get_tool_registry())
    context = ToolContext(tenant_id=tenant_id, db=db, ai_provider=ai_provider)
    reference = await _reference_context(db, ai_provider, prepared)
    result = await orchestrator.run(
        prepared.agent, message, context, history=prepared.history, reference_context=reference
    )
    return await finalize_agent_run(db, prepared, result)


async def stream_agent_run(prepared: PreparedRun) -> AsyncIterator[dict]:
    """Same run as execute_agent_run, as a stream of plain-dict events:
        {"type": "token", "text": ...}   reply text, as it is generated
        {"type": "tool",  "text": name}  a tool is about to run
        {"type": "done",  "data": {...}} the full AgentRunResponse
        {"type": "error", "text": ...}   unexpected failure
    Opens its own DB session: the request-scoped one from `Depends(get_db)`
    may already be closed by the time a streamed response is being sent."""
    try:
        async with async_session_factory() as db:
            ai_provider = get_ai_provider()
            orchestrator = AgentOrchestrator(ai_provider, get_tool_registry())
            context = ToolContext(tenant_id=prepared.tenant_id, db=db, ai_provider=ai_provider)
            reference = await _reference_context(db, ai_provider, prepared)
            async for event in orchestrator.run_stream(
                prepared.agent,
                prepared.message,
                context,
                history=prepared.history,
                reference_context=reference,
            ):
                if event.type == "done":
                    assert event.result is not None
                    response = await finalize_agent_run(db, prepared, event.result)
                    yield {"type": "done", "data": response.model_dump(mode="json")}
                else:
                    yield {"type": event.type, "text": event.text}
    except Exception as exc:  # noqa: BLE001 - a stream can't raise an HTTP error mid-flight
        logger.error("stream_agent_run_failed", error=str(exc))
        yield {"type": "error", "text": "Something went wrong. Please try again."}
