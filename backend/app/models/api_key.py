"""
Agent API keys (spec Section 29/40 spirit: let an external site — the
tenant's own project, "whatever the project" — embed a chat widget that
talks to one specific installed agent, without that external site's
visitors ever being PersonalOps platform users).

The plaintext key is shown to the tenant admin exactly once, at creation —
only its SHA-256 hash is ever stored, the same principle as password
hashing (never store a verifiable secret in recoverable form).
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AgentApiKey(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "agent_api_keys"

    agent_slug: Mapped[str] = mapped_column(String(100), index=True)
    label: Mapped[str] = mapped_column(String(100))
    # Shown in the UI list for identification, e.g. "pak_8f3a9c21..." — not
    # secret on its own (too short to brute-force usefully), just a visible
    # fingerprint so an admin can tell keys apart without re-seeing the full value.
    key_prefix: Mapped[str] = mapped_column(String(20))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
