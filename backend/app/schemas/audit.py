import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditLogOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    event_type: str
    actor: str
    tool_name: str | None
    agent_run_id: uuid.UUID | None
    approval_id: uuid.UUID | None
    status: str
    detail: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}
