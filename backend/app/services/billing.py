"""
Billing service: plan catalog seeding, per-tenant subscription lookup
(lazily creating a default free subscription for tenants that predate this
feature — e.g. every tenant created in Phases 1-10's tests/demos), and
usage calculation.

Usage is computed by counting existing AgentRun rows in the current
calendar-month window, not a separately-incremented counter — one less
place for a count to drift from reality (spec coding standard: avoid
duplicate logic / hidden state that can desync).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_run import AgentRun
from app.models.billing import Plan, SubscriptionStatus, TenantSubscription

# This platform's own commercial tiers — not a fact about any external
# business, so defining them here is an ordinary product decision, not
# "inventing business data" in the sense the spec warns against elsewhere.
DEFAULT_PLANS = [
    {
        "slug": "free",
        "name": "Free",
        "price_usd_per_month": 0.0,
        "max_agent_runs_per_month": 1000,
        "max_tool_calls_per_month": 5000,
        "max_users": 3,
    },
    {
        "slug": "starter",
        "name": "Starter",
        "price_usd_per_month": 29.0,
        "max_agent_runs_per_month": 5000,
        "max_tool_calls_per_month": 25000,
        "max_users": 10,
    },
    {
        "slug": "pro",
        "name": "Pro",
        "price_usd_per_month": 99.0,
        "max_agent_runs_per_month": 50000,
        "max_tool_calls_per_month": 250000,
        "max_users": 50,
    },
]


async def seed_default_plans(db: AsyncSession) -> None:
    """Idempotent — safe to call on every app startup."""
    result = await db.execute(select(Plan.slug))
    existing_slugs = {row[0] for row in result.all()}
    for plan_data in DEFAULT_PLANS:
        if plan_data["slug"] not in existing_slugs:
            db.add(Plan(**plan_data))
    await db.commit()


def current_period_start() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def get_plan_by_slug(db: AsyncSession, slug: str) -> Plan | None:
    # seed_default_plans() is per-slug idempotent (checks existing slugs
    # before inserting), so calling it unconditionally here is always
    # correct — unlike an "is the table empty?" check, it isn't defeated
    # by some other, unrelated Plan row already existing (e.g. a test's
    # own custom plan). Covers the test client, which (unlike the real
    # app) never runs app.main's lifespan seeding step.
    await seed_default_plans(db)
    result = await db.execute(select(Plan).where(Plan.slug == slug))
    return result.scalar_one_or_none()


async def list_plans(db: AsyncSession) -> list[Plan]:
    await seed_default_plans(db)
    result = await db.execute(select(Plan))
    return list(result.scalars().all())


async def get_subscription(db: AsyncSession, tenant_id: uuid.UUID) -> TenantSubscription | None:
    """Read-only lookup — does not create a row. Used for cross-tenant
    admin listings, where lazily writing on every GET would be a surprising
    side effect at scale."""
    result = await db.execute(
        select(TenantSubscription).where(TenantSubscription.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


async def ensure_subscription(db: AsyncSession, tenant_id: uuid.UUID) -> TenantSubscription:
    """Get-or-create — used when a concrete subscription is actually
    needed (enforcement, or the tenant's own billing view)."""
    subscription = await get_subscription(db, tenant_id)
    if subscription is not None:
        return subscription

    free_plan = await get_plan_by_slug(db, "free")  # defensively seeds if needed
    subscription = TenantSubscription(
        tenant_id=tenant_id, plan_id=free_plan.id, status=SubscriptionStatus.ACTIVE
    )
    db.add(subscription)
    await db.commit()
    await db.refresh(subscription)
    return subscription


async def get_agent_run_usage(db: AsyncSession, tenant_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(AgentRun)
        .where(AgentRun.tenant_id == tenant_id, AgentRun.created_at >= current_period_start())
    )
    return result.scalar_one()


async def check_usage_allowed(db: AsyncSession, tenant_id: uuid.UUID) -> tuple[bool, Plan, int]:
    """Returns (allowed, plan, current_agent_run_count)."""
    subscription = await ensure_subscription(db, tenant_id)
    plan_result = await db.execute(select(Plan).where(Plan.id == subscription.plan_id))
    plan = plan_result.scalar_one()
    usage = await get_agent_run_usage(db, tenant_id)
    return usage < plan.max_agent_runs_per_month, plan, usage
