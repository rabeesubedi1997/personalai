"""
A Tenant is one business on the platform (Ghar Nepal, Tolemate, Paradise
Nepal, a future client...). Every tenant-scoped table carries a tenant_id
foreign key back to this table (spec Section 23).
"""
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Tenant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(default=True)
