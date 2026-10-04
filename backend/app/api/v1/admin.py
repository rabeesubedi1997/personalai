"""
Platform-wide multi-tenant administration (spec Section 23/43).

Unlike every other endpoint in this API, this one is intentionally
cross-tenant — it's the one place an operator can see across all
businesses on the platform, gated by role rather than tenant_id. This is
the opposite of tenant isolation on purpose, and restricted to
PLATFORM_ADMIN accordingly (same pattern as the scheduler trigger
endpoint).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.billing import Plan
from app.models.tenant import Tenant
from app.models.user import Role, User
from app.schemas.admin import TenantSummary
from app.security.deps import get_current_user
from app.services.billing import get_agent_run_usage, get_subscription

router = APIRouter()


@router.get("/admin/tenants", response_model=list[TenantSummary])
async def list_all_tenants(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[TenantSummary]:
    if current_user.role != Role.PLATFORM_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only platform admins can view the cross-tenant admin list.",
        )

    tenants = (await db.execute(select(Tenant))).scalars().all()
    summaries = []
    for tenant in tenants:
        user_count = (
            await db.execute(
                select(func.count()).select_from(User).where(User.tenant_id == tenant.id)
            )
        ).scalar_one()

        # Read-only lookup — do not lazily create a subscription just from
        # listing tenants (see services/billing.py's get_subscription docstring).
        subscription = await get_subscription(db, tenant.id)
        plan_slug = None
        if subscription is not None:
            plan = await db.get(Plan, subscription.plan_id)
            plan_slug = plan.slug if plan else None

        usage = await get_agent_run_usage(db, tenant.id)

        summaries.append(
            TenantSummary(
                id=tenant.id,
                name=tenant.name,
                slug=tenant.slug,
                is_active=tenant.is_active,
                user_count=user_count,
                plan_slug=plan_slug,
                current_period_agent_runs=usage,
                created_at=tenant.created_at,
            )
        )
    return summaries
