"""
Agent execution log (spec Section 25/31). Every orchestrator run is
recorded here: what was asked, which agent/model handled it, every tool
call and its result, how it ended, and why — so "what did the agent do"
is always answerable from the database, not just from logs.
"""
import enum
import uuid

from sqlalchemy import JSON, Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AgentRunStatus(str, enum.Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    MAX_ITERATIONS_REACHED = "max_iterations_reached"
    ESCALATED = "escalated"
    # A SENSITIVE/CRITICAL tool call paused the run pending human approval
    # (spec Section 12) — see Approval model. Distinct from ESCALATED
    # (which means "gave up / hit a limit"): AWAITING_APPROVAL is an
    # expected, recoverable pause, not a failure.
    AWAITING_APPROVAL = "awaiting_approval"


class AgentRun(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "agent_runs"

    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    agent_name: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(100), default="")
    request_text: Mapped[str] = mapped_column(Text)
    final_response: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[AgentRunStatus] = mapped_column(Enum(AgentRunStatus))
    iterations: Mapped[int] = mapped_column(default=0)
    tool_call_count: Mapped[int] = mapped_column(default=0)
    # List of {tool, arguments, result_or_error, is_error} dicts, in order.
    tool_trace: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Set by the Phase 10 scheduler once a FAILED/MAX_ITERATIONS_REACHED run
    # has triggered a follow-up notification, so it isn't re-notified every
    # scheduler tick.
    escalation_notified: Mapped[bool] = mapped_column(default=False)
