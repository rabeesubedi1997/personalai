"""
Lets a tenant point a registered business module (Tolemate, Ghar Nepal,
Paradise Nepal, or any future one) at its real API instead of the bundled
mock — no code change or redeploy, just a base URL saved here. This is
the dashboard counterpart to app/connectors/<business>/connector_factory.py,
which is what actually reads these rows at tool-call time.

Adding a brand-new TYPE of business (one with no module yet) still means
writing a BusinessModule in code first (see docs/CONNECTORS.md) — this
endpoint only configures the real/mock switch for modules that already
exist. Platform-admin only, same pattern as billing and agent API keys.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.registry import list_business_modules
from app.db.session import get_db
from app.models.user import Role, User
from app.schemas.business_connectors import (
    AvailableBusinessOut,
    BusinessConnectorOut,
    BusinessConnectorSetRequest,
)
from app.security.deps import get_current_user
from app.services.business_connectors import (
    delete_connector_config,
    get_connector_config,
    list_connector_configs,
    set_connector_config,
)

router = APIRouter()


def _require_platform_admin(user: User) -> None:
    if user.role != Role.PLATFORM_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only platform admins can manage business connectors.",
        )


def _known_slugs() -> dict[str, object]:
    return {module.name: module for module in list_business_modules()}


@router.get("/business-connectors", response_model=list[AvailableBusinessOut])
async def get_business_connectors(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[AvailableBusinessOut]:
    _require_platform_admin(current_user)
    configs = {c.business_slug: c for c in await list_connector_configs(db, current_user.tenant_id)}
    return [
        AvailableBusinessOut(
            business_slug=module.name,
            name=module.name,
            description=module.description,
            connector=(
                BusinessConnectorOut.model_validate(configs[module.name])
                if module.name in configs
                else None
            ),
        )
        for module in list_business_modules()
    ]


@router.put("/business-connectors/{business_slug}", response_model=BusinessConnectorOut)
async def put_business_connector(
    business_slug: str,
    body: BusinessConnectorSetRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BusinessConnectorOut:
    _require_platform_admin(current_user)
    if business_slug not in _known_slugs():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown business '{business_slug}' — no module registered with that slug.",
        )
    if not body.base_url.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="base_url is required")

    record = await set_connector_config(
        db,
        tenant_id=current_user.tenant_id,
        business_slug=business_slug,
        base_url=body.base_url.strip(),
        extra_config=body.extra_config,
    )
    return BusinessConnectorOut.model_validate(record)


@router.delete("/business-connectors/{business_slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_business_connector(
    business_slug: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    _require_platform_admin(current_user)
    existing = await get_connector_config(db, current_user.tenant_id, business_slug)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No connector configured for this business")
    await delete_connector_config(db, current_user.tenant_id, business_slug)
