"""
Agent Marketplace service (spec Section 40/43): browse -> install ->
configure -> test -> deploy, scaled down to what's actually needed today:
browse the catalog, install/uninstall per tenant, enforce it.

The catalog is always derived live from app.agents.registry.list_agents()
— the same registry /api/v1/agents already reads from — so there is one
source of truth for "what agents exist" (code), and one for "what's
installed where" (this table).
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.registry import get_agent, list_agents
from app.db.session import async_session_factory
from app.models.agent_installation import AgentInstallation


async def list_installed(db: AsyncSession, tenant_id: uuid.UUID) -> list[AgentInstallation]:
    result = await db.execute(
        select(AgentInstallation).where(AgentInstallation.tenant_id == tenant_id)
    )
    return list(result.scalars().all())


async def get_installation(
    db: AsyncSession, tenant_id: uuid.UUID, agent_slug: str
) -> AgentInstallation | None:
    result = await db.execute(
        select(AgentInstallation).where(
            AgentInstallation.tenant_id == tenant_id,
            AgentInstallation.agent_slug == agent_slug,
        )
    )
    return result.scalar_one_or_none()


async def is_installed(db: AsyncSession, tenant_id: uuid.UUID, agent_slug: str) -> bool:
    installation = await get_installation(db, tenant_id, agent_slug)
    return installation is not None and installation.is_enabled


async def install_agent(
    db: AsyncSession, tenant_id: uuid.UUID, agent_slug: str
) -> AgentInstallation:
    """Idempotent: installing an already-installed agent just re-enables
    it and refreshes the recorded version."""
    agent = get_agent(agent_slug)
    if agent is None:
        raise ValueError(f"Unknown agent '{agent_slug}'")

    installation = await get_installation(db, tenant_id, agent_slug)
    if installation is None:
        installation = AgentInstallation(
            tenant_id=tenant_id,
            agent_slug=agent_slug,
            version_installed=agent.version,
            is_enabled=True,
        )
        db.add(installation)
    else:
        installation.is_enabled = True
        installation.version_installed = agent.version
    await db.commit()
    await db.refresh(installation)
    return installation


async def uninstall_agent(
    db: AsyncSession, tenant_id: uuid.UUID, agent_slug: str
) -> AgentInstallation | None:
    """Soft-disable, not delete — keeps the installation history auditable
    rather than silently destroying it (spec Section 26 principle applied
    here)."""
    installation = await get_installation(db, tenant_id, agent_slug)
    if installation is None:
        return None
    installation.is_enabled = False
    await db.commit()
    await db.refresh(installation)
    return installation


async def ensure_default_agents_installed(db: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Pre-install every currently-registered agent for a tenant — called
    once at bootstrap, so a new tenant gets the standard catalog without a
    manual install step (spec doesn't require customers to install
    `general_assistant` by hand).

    Only acts if the tenant has NO installation rows at all yet. This is
    deliberately not "always ensure everything is installed" — a tenant
    that has explicitly uninstalled an agent (which leaves a disabled row
    behind) must stay uninstalled; re-running this on every request would
    silently undo that choice and defeat the whole point of the feature.

    The write happens on its own dedicated session, not `db` — same reason
    as `billing.seed_default_plans`: rolling back the shared/caller session
    on a conflict would expire every object already loaded on it (e.g.
    `current_user`), crashing the next plain attribute access elsewhere in
    the request with `MissingGreenlet`.
    """
    existing = await list_installed(db, tenant_id)
    if existing:
        return
    rows = [
        AgentInstallation(
            tenant_id=tenant_id,
            agent_slug=agent.name,
            version_installed=agent.version,
            is_enabled=True,
        )
        for agent in list_agents()
    ]
    try:
        async with async_session_factory() as write_db:
            write_db.add_all(rows)
            await write_db.commit()
    except IntegrityError:
        # A concurrent request for this same brand-new tenant won first and
        # already inserted these rows — the desired end state (full catalog
        # installed) is already true, nothing more to do.
        pass
