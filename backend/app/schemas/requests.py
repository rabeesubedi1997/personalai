import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.request import RequestStatus


class RequestCreate(BaseModel):
    request_type: str
    customer: dict[str, Any] = {}
    requirements: dict[str, Any] = {}
    assigned_agent: str | None = None


class RequestStatusUpdate(BaseModel):
    status: RequestStatus
    note: str | None = None


class RequestOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    request_type: str
    status: RequestStatus
    assigned_agent: str | None
    customer: dict[str, Any]
    requirements: dict[str, Any]
    result: dict[str, Any] | None
    error: str | None
    status_history: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
