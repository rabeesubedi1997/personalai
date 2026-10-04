import uuid
from datetime import datetime

from pydantic import BaseModel


class ApiKeyCreateRequest(BaseModel):
    agent_slug: str
    label: str


class ApiKeyOut(BaseModel):
    id: uuid.UUID
    agent_slug: str
    label: str
    key_prefix: str
    is_active: bool
    last_used_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ApiKeyCreatedOut(ApiKeyOut):
    # Only ever present in the response to the create call — never stored,
    # never returned again afterward.
    api_key: str
