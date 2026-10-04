"""
Agent Marketplace endpoints (spec Section 40/43): browse the catalog,
install/uninstall for the caller's tenant. The catalog is always every
agent currently registered in code (app.agents.registry) — including any
agent a future BusinessModule adds — so a new business plugged in via the
Phase 6 mechanism automatically appears here too, with no marketplace-side
change needed.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.registry import get_agent, list_agents
from app.db.session import get_db
from app.models.user import User
from app.schemas.marketplace import InstalledAgentOut, MarketplaceAgentOut
from app.security.deps import get_current_user
from app.services.marketplace import (
    get_installation,
    install_agent,
    is_installed,
    list_installed,
    uninstall_agent,
)

router = APIRouter()


@router.get("/marketplace/agents", response_model=list[MarketplaceAgentOut])
async def browse_marketplace(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[MarketplaceAgentOut]:
    out = []
    for agent in list_agents():
        installed = await is_installed(db, current_user.tenant_id, agent.name)
        out.append(
            MarketplaceAgentOut(
                slug=agent.name,
                name=agent.name,
                description=agent.description,
                category=agent.category,
                version=agent.version,
                installed=installed,
            )
        )
    return out


@router.get("/marketplace/installed", response_model=list[InstalledAgentOut])
async def list_my_installed_agents(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[InstalledAgentOut]:
    installations = await list_installed(db, current_user.tenant_id)
    out = []
    for installation in installations:
        agent = get_agent(installation.agent_slug)
        out.append(
            InstalledAgentOut(
                slug=installation.agent_slug,
                name=agent.name if agent else installation.agent_slug,
                description=agent.description if agent else "",
                category=agent.category if agent else "unknown",
                version_installed=installation.version_installed,
                is_enabled=installation.is_enabled,
            )
        )
    return out


@router.post("/marketplace/agents/{slug}/install", response_model=InstalledAgentOut)
async def install(
    slug: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InstalledAgentOut:
    agent = get_agent(slug)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown agent '{slug}'")
    installation = await install_agent(db, current_user.tenant_id, slug)
    return InstalledAgentOut(
        slug=slug,
        name=agent.name,
        description=agent.description,
        category=agent.category,
        version_installed=installation.version_installed,
        is_enabled=installation.is_enabled,
    )


@router.post("/marketplace/agents/{slug}/uninstall", response_model=InstalledAgentOut)
async def uninstall(
    slug: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InstalledAgentOut:
    existing = await get_installation(db, current_user.tenant_id, slug)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{slug}' is not installed for this tenant.",
        )
    installation = await uninstall_agent(db, current_user.tenant_id, slug)
    agent = get_agent(slug)
    return InstalledAgentOut(
        slug=slug,
        name=agent.name if agent else slug,
        description=agent.description if agent else "",
        category=agent.category if agent else "unknown",
        version_installed=installation.version_installed,
        is_enabled=installation.is_enabled,
    )
