import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.approval import ApprovalStatus


class ApprovalOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    agent_run_id: uuid.UUID | None
    agent_name: str
    tool_name: str
    arguments: dict[str, Any]
    status: ApprovalStatus
    decided_by_user_id: uuid.UUID | None
    decision_note: str | None
    result: dict[str, Any] | None
    error: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ApprovalDecision(BaseModel):
    note: str | None = None
