"""
"Connect a website" endpoints: give the platform a URL and its content becomes
the knowledge the chat agents answer from. Any site, no per-site code.
Platform-admin only, same as the other integration-management endpoints.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.knowledge_site import SiteStatus
from app.models.user import Role, User
from app.schemas.sites import SiteCreatedOut, SiteCreateRequest, SiteOut
from app.security.deps import get_current_user
from app.services.ai.factory import get_ai_provider
from app.services.api_keys import create_api_key
from app.services.marketplace import ensure_default_agents_installed, install_agent
from app.services.site_knowledge import (
    create_site,
    delete_site,
    get_site,
    list_sites,
    start_ingest_in_background,
)
from app.services.site_knowledge.crawler import CrawlError, check_url_allowed

router = APIRouter()

SITE_AGENT_SLUG = "site_assistant"


def _require_platform_admin(user: User) -> None:
    if user.role != Role.PLATFORM_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only platform admins can manage connected websites.",
        )


@router.post("/sites", response_model=SiteCreatedOut, status_code=status.HTTP_202_ACCEPTED)
async def connect_site(
    body: SiteCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SiteCreatedOut:
    """Starts indexing in the background and returns immediately; poll
    GET /sites/{id} until status is `ready` (or `failed`, with `error`)."""
    _require_platform_admin(current_user)
    url = str(body.url)
    try:
        await check_url_allowed(url)
    except CrawlError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    site = await create_site(
        db,
        tenant_id=current_user.tenant_id,
        url=url,
        name=body.name,
        max_pages=body.max_pages,
        render_js=body.render_js,
    )
    start_ingest_in_background(site.id, get_ai_provider())

    out = SiteCreatedOut.model_validate(site)
    if body.create_widget_key:
        await ensure_default_agents_installed(db, current_user.tenant_id)
        # ensure_default... only acts for brand-new tenants, so an older
        # account would otherwise get a key for an agent it doesn't have
        # installed (the key would 404 on first chat). Installing is
        # idempotent and is exactly what the admin asked for here.
        await install_agent(db, current_user.tenant_id, SITE_AGENT_SLUG)
        _, raw_key = await create_api_key(
            db,
            tenant_id=current_user.tenant_id,
            agent_slug=SITE_AGENT_SLUG,
            label=f"Website chat: {site.name}",
        )
        out.api_key = raw_key
        out.agent_slug = SITE_AGENT_SLUG
    return out


@router.get("/sites", response_model=list[SiteOut])
async def get_sites(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[SiteOut]:
    _require_platform_admin(current_user)
    return [SiteOut.model_validate(s) for s in await list_sites(db, current_user.tenant_id)]


@router.get("/sites/{site_id}", response_model=SiteOut)
async def get_one_site(
    site_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SiteOut:
    _require_platform_admin(current_user)
    site = await get_site(db, current_user.tenant_id, site_id)
    if site is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found")
    return SiteOut.model_validate(site)


@router.post("/sites/{site_id}/recrawl", response_model=SiteOut, status_code=status.HTTP_202_ACCEPTED)
async def recrawl_site(
    site_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SiteOut:
    _require_platform_admin(current_user)
    site = await get_site(db, current_user.tenant_id, site_id)
    if site is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found")
    if site.status == SiteStatus.CRAWLING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This site is already being indexed."
        )
    site.status = SiteStatus.PENDING
    await db.commit()
    await db.refresh(site)
    start_ingest_in_background(site.id, get_ai_provider())
    return SiteOut.model_validate(site)


@router.delete("/sites/{site_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_site(
    site_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    _require_platform_admin(current_user)
    site = await get_site(db, current_user.tenant_id, site_id)
    if site is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found")
    await delete_site(db, site)
