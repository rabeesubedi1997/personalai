"""
"Connect AI Agent" endpoints — issue/revoke API keys that let an external
site (the tenant's own project, or any future project) embed a chat widget
talking to one specific installed agent via POST /api/v1/public/chat,
without that external site's visitors needing a PersonalOps login.
Platform-admin only, same pattern as billing plan switching.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.registry import get_agent
from app.db.session import get_db
from app.models.user import Role, User
from app.schemas.api_keys import ApiKeyCreatedOut, ApiKeyCreateRequest, ApiKeyOut
from app.security.deps import get_current_user
from app.services.api_keys import create_api_key, list_api_keys, revoke_api_key
from app.services.marketplace import is_installed

router = APIRouter()


def _require_platform_admin(user: User) -> None:
    if user.role != Role.PLATFORM_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only platform admins can manage agent API keys.",
        )


@router.get("/integrations/api-keys", response_model=list[ApiKeyOut])
async def get_api_keys(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[ApiKeyOut]:
    _require_platform_admin(current_user)
    keys = await list_api_keys(db, current_user.tenant_id)
    return [ApiKeyOut.model_validate(k) for k in keys]


@router.post(
    "/integrations/api-keys", response_model=ApiKeyCreatedOut, status_code=status.HTTP_201_CREATED
)
async def create_agent_api_key(
    body: ApiKeyCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiKeyCreatedOut:
    _require_platform_admin(current_user)

    agent = get_agent(body.agent_slug)
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown agent '{body.agent_slug}'"
        )
    if not await is_installed(db, current_user.tenant_id, body.agent_slug):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Agent '{body.agent_slug}' is not installed for this tenant. "
                "Install it first via the Marketplace."
            ),
        )

    record, raw_key = await create_api_key(
        db, tenant_id=current_user.tenant_id, agent_slug=body.agent_slug, label=body.label
    )
    return ApiKeyCreatedOut(
        id=record.id,
        agent_slug=record.agent_slug,
        label=record.label,
        key_prefix=record.key_prefix,
        is_active=record.is_active,
        last_used_at=record.last_used_at,
        created_at=record.created_at,
        api_key=raw_key,
    )


@router.delete("/integrations/api-keys/{key_id}", response_model=ApiKeyOut)
async def delete_api_key(
    key_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiKeyOut:
    _require_platform_admin(current_user)
    record = await revoke_api_key(db, tenant_id=current_user.tenant_id, key_id=key_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    return ApiKeyOut.model_validate(record)
