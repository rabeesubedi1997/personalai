import uuid
from datetime import datetime

from pydantic import BaseModel


class BusinessConnectorSetRequest(BaseModel):
    base_url: str
    extra_config: dict | None = None


class BusinessConnectorOut(BaseModel):
    id: uuid.UUID
    business_slug: str
    base_url: str
    is_enabled: bool
    extra_config: dict | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AvailableBusinessOut(BaseModel):
    """One registered BusinessModule the tenant could configure a real
    connector for, with whatever config it currently has (if any)."""

    business_slug: str
    name: str
    description: str
    connector: BusinessConnectorOut | None
