"""
Audit log (spec Section 25). Focused on security-relevant and
human-decision events — denied tool calls, and every approval
request/decision/execution — rather than duplicating the full
turn-by-turn trace already captured in AgentRun.tool_trace. Must answer:
"what did the agent do, why, which tool, what result, who approved it."
Never store secrets here.
"""
import uuid

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AuditLog(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "audit_logs"

    event_type: Mapped[str] = mapped_column(String(100), index=True)
    # "agent:<name>" or a user id string — whoever/whatever triggered this.
    actor: Mapped[str] = mapped_column(String(255))
    tool_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    approval_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(50))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
