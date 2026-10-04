"""
User + Role foundation (spec Section 24: Platform Admin, Tenant Owner,
Business Admin, Manager, Staff, Agent Operator, Viewer).

Phase 1 ships the minimum needed for login + tenant scoping; fine-grained
per-tool/per-agent permission checks are layered on in Phase 5.
"""
import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Role(str, enum.Enum):
    PLATFORM_ADMIN = "platform_admin"
    TENANT_OWNER = "tenant_owner"
    BUSINESS_ADMIN = "business_admin"
    MANAGER = "manager"
    STAFF = "staff"
    AGENT_OPERATOR = "agent_operator"
    VIEWER = "viewer"


class User(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255), default="")
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.VIEWER)
    is_active: Mapped[bool] = mapped_column(default=True)
