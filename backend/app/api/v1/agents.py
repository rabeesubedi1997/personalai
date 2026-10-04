import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.registry import get_agent, list_agents
from app.db.session import get_db
from app.models.agent_run import AgentRun
from app.models.user import User
from app.schemas.agents import AgentInfo, AgentRunRequest, AgentRunResponse, ToolInfo
from app.security.deps import get_current_user
from app.services.agent_execution import execute_agent_run
from app.services.marketplace import ensure_default_agents_installed, is_installed
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
    return await execute_agent_run(
        db,
        tenant_id=current_user.tenant_id,
        acting_user_id=current_user.id,
        agent_slug=body.agent,
        message=body.message,
        conversation_id=body.conversation_id,
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
