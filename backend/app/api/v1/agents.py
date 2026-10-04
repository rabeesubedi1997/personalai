from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.registry import get_agent, list_agents
from app.db.session import get_db
from app.models.agent_run import AgentRun
from app.models.user import User
from app.orchestrator import AgentOrchestrator
from app.schemas.agents import AgentInfo, AgentRunRequest, AgentRunResponse, ToolInfo
from app.security.deps import get_current_user
from app.services.ai.factory import get_ai_provider
from app.tools.registry import get_tool_registry

router = APIRouter()


@router.get("/agents", response_model=list[AgentInfo])
async def list_available_agents(_user: User = Depends(get_current_user)) -> list[AgentInfo]:
    return [
        AgentInfo(name=a.name, description=a.description, allowed_tools=a.allowed_tools)
        for a in list_agents()
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

    orchestrator = AgentOrchestrator(get_ai_provider(), get_tool_registry())
    result = await orchestrator.run(agent, body.message)

    run = AgentRun(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
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

    return AgentRunResponse(
        run_id=run.id,
        agent=agent.name,
        status=result.status,
        final_response=result.final_response,
        iterations=result.iterations,
        tool_trace=result.tool_trace,
        model=result.model,
        error=result.error,
    )
