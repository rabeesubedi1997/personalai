"""Declarative base shared by every ORM model, plus common mixins."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class TenantScopedMixin:
    """
    Mixed into every table that holds tenant-owned data (spec Section 23:
    "Every relevant record must be tenant-aware... Tenant data must never
    leak between businesses"). Queries against tenant-scoped tables must
    always filter on tenant_id — see app.security.tenant for the enforced
    query helper.
    """
    tenant_id: Mapped[uuid.UUID] = mapped_column(index=True)
