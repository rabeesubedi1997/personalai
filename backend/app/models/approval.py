"""
Human Approval Engine (spec Section 12). SENSITIVE/CRITICAL tools never
execute immediately — see Tool.requires_approval and
ToolRegistry.execute() — they create a row here instead, and only run once
a human approves it (POST /api/v1/approvals/{id}/approve).

This is deliberately business-agnostic: `tool_name` + `arguments` is enough
to describe "cancel booking #123" for Tolemate, "cancel viewing request
#456" for Ghar Nepal, or any future business's sensitive action — nothing
here is Tolemate/GharNepal/ParadiseNepal-specific.
"""
import enum
import uuid

from sqlalchemy import JSON, Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    REJECTED = "rejected"
    EXECUTED = "executed"  # approved AND successfully executed
    FAILED = "failed"  # approved but the tool execution itself failed


class Approval(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "approvals"

    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    agent_name: Mapped[str] = mapped_column(String(100))
    tool_name: Mapped[str] = mapped_column(String(100))
    arguments: Mapped[dict] = mapped_column(JSON, default=dict)
    # Snapshot of the requesting agent's allow-list at request time, so the
    # eventual execute-on-approve still goes through the same permission
    # check rather than silently trusting a stale/changed agent definition.
    allowed_tool_names: Mapped[list] = mapped_column(JSON, default=list)

    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus), default=ApprovalStatus.PENDING, index=True
    )
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
