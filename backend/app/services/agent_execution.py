"""
Shared agent-run execution path, used by BOTH the internal (JWT-authenticated
dashboard user) `POST /api/v1/agents/run` and the public (API-key-authenticated
external widget) `POST /api/v1/public/chat`. Extracted so the two entry
points can never drift apart on billing enforcement, install checks,
conversation handling, or approval/notification wiring — one implementation,
two callers with different auth in front of it.
"""
from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.registry import get_agent
from app.models.agent_run import AgentRun, AgentRunStatus
from app.models.approval import Approval
from app.models.notification import NotificationChannel
from app.orchestrator import AgentOrchestrator
from app.schemas.agents import AgentRunResponse
from app.services.ai.factory import get_ai_provider
from app.services.billing import check_usage_allowed
from app.services.conversation_store import ConversationStore
from app.services.marketplace import ensure_default_agents_installed, is_installed
from app.services.notifications.service import NotificationService
from app.tools.base import ToolContext
from app.tools.registry import get_tool_registry


async def execute_agent_run(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    acting_user_id: uuid.UUID,
    agent_slug: str,
    message: str,
    conversation_id: uuid.UUID | None,
) -> AgentRunResponse:
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
    conversation_store = ConversationStore(db)
    history = (
        await conversation_store.load(tenant_id=tenant_id, conversation_id=resolved_conversation_id)
        if conversation_id is not None
        else []
    )

    ai_provider = get_ai_provider()
    orchestrator = AgentOrchestrator(ai_provider, get_tool_registry())
    context = ToolContext(tenant_id=tenant_id, db=db, ai_provider=ai_provider)
    result = await orchestrator.run(agent, message, context, history=history)

    await conversation_store.append(
        tenant_id=tenant_id,
        conversation_id=resolved_conversation_id,
        messages=result.new_messages,
    )

    run = AgentRun(
        tenant_id=tenant_id,
        user_id=acting_user_id,
        conversation_id=resolved_conversation_id,
        agent_name=agent.name,
        model=result.model,
        request_text=message,
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
            user_id=acting_user_id,
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
        conversation_id=resolved_conversation_id,
    )
