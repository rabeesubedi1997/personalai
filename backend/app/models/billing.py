"""
SaaS billing architecture (spec Section 11/23/43): subscription plans,
usage limits, per-tenant subscriptions. No real payment processor is
integrated (no Stripe/payment credentials exist or are invented) — plan
"selection" here is self-service and free of real payment, same
mock-now-swap-later rule as everything else lacking real external access.
The plan tiers themselves (names, limits, prices) are this platform's own
commercial model, not a fact about any external business, so defining them
in code is not "inventing business data" in the sense the spec warns
against elsewhere.
"""
import enum
import uuid

from sqlalchemy import Enum, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"
    TRIAL = "trial"
    CANCELLED = "cancelled"


class Plan(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A plan is platform-wide, not tenant-scoped — every tenant can see
    and select from the same catalog."""

    __tablename__ = "plans"

    slug: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    price_usd_per_month: Mapped[float] = mapped_column(Float, default=0.0)
    max_agent_runs_per_month: Mapped[int] = mapped_column(Integer)
    max_tool_calls_per_month: Mapped[int] = mapped_column(Integer)
    max_users: Mapped[int] = mapped_column(Integer)


class TenantSubscription(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One row per tenant — not a TenantScopedMixin table, since this IS
    the tenant-to-plan relationship itself, not tenant-owned data."""

    __tablename__ = "tenant_subscriptions"

    tenant_id: Mapped[uuid.UUID] = mapped_column(unique=True, index=True)
    plan_id: Mapped[uuid.UUID] = mapped_column(index=True)
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus), default=SubscriptionStatus.ACTIVE
    )
