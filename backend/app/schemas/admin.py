import uuid
from datetime import datetime

from pydantic import BaseModel


class TenantSummary(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    is_active: bool
    user_count: int
    plan_slug: str | None
    current_period_agent_runs: int
    created_at: datetime
