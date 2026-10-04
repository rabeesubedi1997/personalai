"""
Resolves which Tolemate connector a tool call should use: the real one, if
this tenant has configured and enabled one, else the bundled mock — so a
brand-new tenant (or any tenant that never configures a real connection)
keeps working exactly as before, with zero behavior change.
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Protocol

from app.connectors.tolemate.connector import tolemate_connector
from app.connectors.tolemate.real_connector import RealTolemateConnector
from app.services.business_connectors import get_connector_config

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

BUSINESS_SLUG = "tolemate"


class TolemateConnectorLike(Protocol):
    async def asearch_providers(self, service: str, location: str | None = None) -> list[dict]: ...
    async def acheck_availability(self, provider_id: str, date: str) -> bool: ...
    async def acreate_booking(
        self,
        provider_id: str,
        date: str,
        customer_name: str,
        notes: str = "",
        customer_email: str | None = None,
    ) -> dict: ...


async def get_connector(db: "AsyncSession", tenant_id: uuid.UUID) -> TolemateConnectorLike:
    config = await get_connector_config(db, tenant_id, BUSINESS_SLUG)
    if config is not None and config.is_enabled and config.base_url:
        return RealTolemateConnector(config.base_url)
    return tolemate_connector
