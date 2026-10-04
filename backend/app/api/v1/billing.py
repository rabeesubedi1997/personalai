"""
Billing endpoints (spec Section 11/23/43). No real payment processor is
integrated — switching plans here is self-service plan *selection*, not a
real charge. Swapping in real billing (Stripe or similar) later means
adding a payment step before the plan switch commits; the plan/usage model
underneath doesn't change.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import Role, User
from app.schemas.billing import PlanOut, SubscriptionOut, SubscriptionUpdateRequest
from app.security.deps import get_current_user
from app.models.billing import Plan
from app.services.billing import (
    ensure_subscription,
    get_agent_run_usage,
    get_plan_by_slug,
    list_plans,
)

router = APIRouter()


@router.get("/billing/plans", response_model=list[PlanOut])
async def get_plans(
    _user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[PlanOut]:
    plans = await list_plans(db)
    return [PlanOut.model_validate(p) for p in plans]


@router.get("/billing/subscription", response_model=SubscriptionOut)
async def get_my_subscription(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> SubscriptionOut:
    subscription = await ensure_subscription(db, current_user.tenant_id)
    plan = await db.get(Plan, subscription.plan_id)
    usage = await get_agent_run_usage(db, current_user.tenant_id)
    return SubscriptionOut(
        tenant_id=current_user.tenant_id,
        plan=PlanOut.model_validate(plan),
        status=subscription.status,
        current_period_agent_runs=usage,
    )


@router.post("/billing/subscription", response_model=SubscriptionOut)
async def update_my_subscription(
    body: SubscriptionUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionOut:
    if current_user.role != Role.PLATFORM_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a platform admin can change the tenant's plan.",
        )
    plan = await get_plan_by_slug(db, body.plan_slug)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown plan '{body.plan_slug}'"
        )

    subscription = await ensure_subscription(db, current_user.tenant_id)
    subscription.plan_id = plan.id
    await db.commit()

    usage = await get_agent_run_usage(db, current_user.tenant_id)
    return SubscriptionOut(
        tenant_id=current_user.tenant_id,
        plan=PlanOut.model_validate(plan),
        status=subscription.status,
        current_period_agent_runs=usage,
    )
