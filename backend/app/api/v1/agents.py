import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.registry import get_agent, list_agents
from app.db.session import get_db
from app.models.agent_run import AgentRun, AgentRunStatus
from app.models.approval import Approval
from app.models.notification import NotificationChannel
from app.models.user import User
from app.orchestrator import AgentOrchestrator
from app.schemas.agents import AgentInfo, AgentRunRequest, AgentRunResponse, ToolInfo
from app.security.deps import get_current_user
from app.services.ai.factory import get_ai_provider
from app.services.billing import check_usage_allowed
from app.services.conversation_store import ConversationStore
from app.services.marketplace import ensure_default_agents_installed, is_installed
from app.services.notifications.service import NotificationService
from app.tools.base import ToolContext
from app.tools.registry import get_tool_registry

router = APIRouter()


@router.get("/agents", response_model=list[AgentInfo])
async def list_available_agents(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[AgentInfo]:
    """Lists only agents installed for the caller's tenant (spec Section
    40: marketplace install/activate) — not every agent that exists in
    code. See POST /api/v1/marketplace/agents/{slug}/install."""
    await ensure_default_agents_installed(db, current_user.tenant_id)
    return [
        AgentInfo(name=a.name, description=a.description, allowed_tools=a.allowed_tools)
        for a in list_agents()
        if await is_installed(db, current_user.tenant_id, a.name)
    ]


@router.get("/tools", response_model=list[ToolInfo])
async def list_available_tools(_user: User = Depends(get_current_user)) -> list[ToolInfo]:
    registry = get_tool_registry()
    tools = [registry.get(name) for name in registry.all_names()]
    return [
        ToolInfo(
            name=t.name,
            description=t.description,
            permission_level=t.permission_level.value,
            requires_approval=t.requires_approval,
        )
        for t in tools
        if t is not None
    ]


@router.post("/agents/run", response_model=AgentRunResponse)
async def run_agent(
    body: AgentRunRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentRunResponse:
    agent = get_agent(body.agent)
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown agent '{body.agent}'"
        )

    await ensure_default_agents_installed(db, current_user.tenant_id)
    if not await is_installed(db, current_user.tenant_id, agent.name):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Agent '{agent.name}' is not installed for this tenant. "
                "Install it via POST /api/v1/marketplace/agents/{slug}/install first."
            ),
        )

    allowed, plan, usage = await check_usage_allowed(db, current_user.tenant_id)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"Monthly agent run limit reached for the '{plan.name}' plan "
                f"({usage}/{plan.max_agent_runs_per_month}). Upgrade your plan to continue."
            ),
        )

    conversation_id = body.conversation_id or uuid.uuid4()
    conversation_store = ConversationStore(db)
    history = (
        await conversation_store.load(
            tenant_id=current_user.tenant_id, conversation_id=conversation_id
        )
        if body.conversation_id is not None
        else []
    )

    ai_provider = get_ai_provider()
    orchestrator = AgentOrchestrator(ai_provider, get_tool_registry())
    context = ToolContext(tenant_id=current_user.tenant_id, db=db, ai_provider=ai_provider)
    result = await orchestrator.run(agent, body.message, context, history=history)

    await conversation_store.append(
        tenant_id=current_user.tenant_id,
        conversation_id=conversation_id,
        messages=result.new_messages,
    )

    run = AgentRun(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        conversation_id=conversation_id,
        agent_name=agent.name,
        model=result.model,
        request_text=body.message,
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
            tenant_id=current_user.tenant_id,
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
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
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
        conversation_id=conversation_id,
    )


@router.get("/agents/runs", response_model=list[AgentRunResponse])
async def list_agent_runs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AgentRunResponse]:
    """Query surface for spec Section 25/31: 'what did the agent do.'
    Tenant-scoped like everything else."""
    result = await db.execute(
        select(AgentRun)
        .where(AgentRun.tenant_id == current_user.tenant_id)
        .order_by(AgentRun.created_at.desc())
    )
    runs = result.scalars().all()
    return [
        AgentRunResponse(
            run_id=r.id,
            agent=r.agent_name,
            status=r.status,
            final_response=r.final_response,
            iterations=r.iterations,
            tool_trace=r.tool_trace,
            model=r.model,
            error=r.error,
            conversation_id=r.conversation_id,
        )
        for r in runs
    ]


@router.get("/agents/runs/{run_id}", response_model=AgentRunResponse)
async def get_agent_run(
    run_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentRunResponse:
    result = await db.execute(
        select(AgentRun).where(
            AgentRun.id == run_id, AgentRun.tenant_id == current_user.tenant_id
        )
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found")
    return AgentRunResponse(
        run_id=run.id,
        agent=run.agent_name,
        status=run.status,
        final_response=run.final_response,
        iterations=run.iterations,
        tool_trace=run.tool_trace,
        model=run.model,
        error=run.error,
        conversation_id=run.conversation_id,
    )
