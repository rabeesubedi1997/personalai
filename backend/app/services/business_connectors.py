"""
CRUD for per-tenant BusinessConnectorConfig rows — the dynamic "point this
business module at a real API" settings used by
app/connectors/<business>/connector_factory.py and the dashboard's
Integrations screen (app/api/v1/business_connectors.py).
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business_connector import BusinessConnectorConfig


async def get_connector_config(
    db: AsyncSession, tenant_id: uuid.UUID, business_slug: str
) -> BusinessConnectorConfig | None:
    result = await db.execute(
        select(BusinessConnectorConfig).where(
            BusinessConnectorConfig.tenant_id == tenant_id,
            BusinessConnectorConfig.business_slug == business_slug,
        )
    )
    return result.scalar_one_or_none()


async def list_connector_configs(
    db: AsyncSession, tenant_id: uuid.UUID
) -> list[BusinessConnectorConfig]:
    result = await db.execute(
        select(BusinessConnectorConfig)
        .where(BusinessConnectorConfig.tenant_id == tenant_id)
        .order_by(BusinessConnectorConfig.business_slug)
    )
    return list(result.scalars().all())


async def set_connector_config(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    business_slug: str,
    base_url: str,
    extra_config: dict | None = None,
) -> BusinessConnectorConfig:
    existing = await get_connector_config(db, tenant_id, business_slug)
    if existing is not None:
        existing.base_url = base_url
        existing.extra_config = extra_config
        existing.is_enabled = True
        await db.commit()
        await db.refresh(existing)
        return existing

    record = BusinessConnectorConfig(
        tenant_id=tenant_id,
        business_slug=business_slug,
        base_url=base_url,
        extra_config=extra_config,
        is_enabled=True,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def delete_connector_config(
    db: AsyncSession, tenant_id: uuid.UUID, business_slug: str
) -> bool:
    """Removes the config entirely — the business module falls straight
    back to its mock connector, same as a tenant that never configured one."""
    existing = await get_connector_config(db, tenant_id, business_slug)
    if existing is None:
        return False
    await db.delete(existing)
    await db.commit()
    return True
