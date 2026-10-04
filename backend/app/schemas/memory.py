import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.memory import MemoryType


class MemoryCreate(BaseModel):
    memory_type: MemoryType
    content: str
    subject_id: str | None = None
    metadata: dict[str, Any] = {}


class MemoryOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    memory_type: MemoryType
    subject_id: str | None
    content: str
    metadata: dict[str, Any] = Field(validation_alias="record_metadata")
    created_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class MemorySearchRequest(BaseModel):
    query: str
    memory_type: MemoryType | None = None
    top_k: int = 5


class MemorySearchResult(BaseModel):
    memory: MemoryOut
    score: float
