import uuid

from pydantic import BaseModel

from app.models.billing import SubscriptionStatus


class PlanOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    price_usd_per_month: float
    max_agent_runs_per_month: int
    max_tool_calls_per_month: int
    max_users: int

    model_config = {"from_attributes": True}


class SubscriptionOut(BaseModel):
    tenant_id: uuid.UUID
    plan: PlanOut
    status: SubscriptionStatus
    current_period_agent_runs: int


class SubscriptionUpdateRequest(BaseModel):
    plan_slug: str
