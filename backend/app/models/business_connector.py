"""
Per-tenant configuration for a business module's REAL connector (as
opposed to the bundled mock one each module ships with — see
app/connectors/<business>/connector.py).

A business module (Tolemate, Ghar Nepal, Paradise Nepal, or a future one)
is always registered in code (app/connectors/__init__.py) — that part
never changes per tenant. What DOES vary per tenant is whether that
tenant has pointed the module at a real, live API yet, and at what URL.
This table holds exactly that, so flipping a business from mock to real
(or onboarding a second tenant with a different real deployment of the
same business type) never requires a code change or redeploy — just a row
here, set from the dashboard (see app/api/v1/business_connectors.py).

No credentials column yet: Tolemate's real API needs none (its search and
availability routes are public, and booking uses a just-in-time customer
account — see app/connectors/tolemate/real_connector.py). A future
business module whose real API needs an API key would add a nullable
column here when that's actually built, not speculatively now.
"""
from sqlalchemy import JSON, Boolean, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class BusinessConnectorConfig(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "business_connector_configs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "business_slug", name="uq_tenant_business_connector"),
    )

    # Matches a registered BusinessModule.name (e.g. "tolemate") — validated
    # against app.connectors.registry.list_business_modules() at write time,
    # not enforced at the DB layer, since the set of valid slugs is a
    # runtime/code concern, not a schema concern.
    business_slug: Mapped[str] = mapped_column(String(50), index=True)
    base_url: Mapped[str] = mapped_column(String(500))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Free-form, business-specific tuning (e.g. a default search radius_km
    # for a business whose real API — like Tolemate's — has no city field).
    extra_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
