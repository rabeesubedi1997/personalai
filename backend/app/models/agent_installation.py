"""
Agent Marketplace installations (spec Section 40/43): which agents a
tenant has activated. The catalog itself isn't a DB table — it's derived
live from the code-registered agent registry (app/agents/registry.py),
so there's one source of truth for "what agents exist," not two that can
drift apart. This table only tracks the tenant-specific "is it installed"
relationship.
"""
import uuid

from sqlalchemy import Boolean, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AgentInstallation(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "agent_installations"
    __table_args__ = (UniqueConstraint("tenant_id", "agent_slug", name="uq_tenant_agent"),)

    agent_slug: Mapped[str] = mapped_column(String(100), index=True)
    version_installed: Mapped[str] = mapped_column(String(20), default="1.0.0")
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
