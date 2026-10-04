"""
Universal Request Engine (spec Section 13). A Request is the generic unit
of work that flows through the platform regardless of which business or
agent handles it — a Tolemate booking, a Ghar Nepal enquiry, and a future
hotel reservation all use this same table and the same lifecycle.
"""
import enum
import uuid

from sqlalchemy import JSON, Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class RequestStatus(str, enum.Enum):
    RECEIVED = "received"
    UNDERSTANDING = "understanding"
    NEEDS_INFORMATION = "needs_information"
    VALIDATING = "validating"
    SEARCHING = "searching"
    MATCHING = "matching"
    WAITING_FOR_CONFIRMATION = "waiting_for_confirmation"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    # Terminal, reachable from most non-terminal states (spec Section 13)
    CANCELLED = "cancelled"
    FAILED = "failed"
    ESCALATED = "escalated"


TERMINAL_STATUSES = {
    RequestStatus.COMPLETED,
    RequestStatus.CANCELLED,
    RequestStatus.FAILED,
    RequestStatus.ESCALATED,
}


class Request(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "requests"

    # Not an enum/foreign key on purpose — request_type is open-ended so a
    # new business (hotel, e-commerce, ...) never requires a core schema
    # change (spec Section 15/19: "adding a new business should not require
    # rewriting the core platform").
    request_type: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[RequestStatus] = mapped_column(
        Enum(RequestStatus), default=RequestStatus.RECEIVED, index=True
    )
    assigned_agent: Mapped[str | None] = mapped_column(String(100), nullable=True)

    customer: Mapped[dict] = mapped_column(JSON, default=dict)
    requirements: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Free-form history of status transitions: [{from, to, note, at}, ...]
    # — a lightweight in-row audit trail; the full agent_runs table remains
    # the authoritative execution log for anything AI-driven.
    status_history: Mapped[list] = mapped_column(JSON, default=list)
