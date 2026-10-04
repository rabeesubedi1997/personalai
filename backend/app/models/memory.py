"""
Memory system (spec Section 14). One table, four memory "kinds" plus a
knowledge base, distinguished by `memory_type` + free-form `subject_id`
(e.g. a customer id, a conversation id, or null for business-wide/knowledge
entries) — not four separate tables, since they share the same shape
(content + embedding + metadata) and the same tenant-isolation requirement.

Storage note (documented assumption, spec Section 51): the `embedding`
column is plain JSON (a list of floats) because the Phase 1-4 default
DATABASE_URL is SQLite, which has no vector type. Similarity search is
therefore done in Python (app/memory/store.py), which is fine at
dev/demo record counts but does NOT scale — when DATABASE_URL points at
PostgreSQL, this column should become pgvector's `Vector` type and
searches should use its indexed `<->` operator instead. Flagged here
rather than silently shipped as if it were the production design.
"""
import enum
import uuid

from sqlalchemy import JSON, Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class MemoryType(str, enum.Enum):
    CONVERSATION = "conversation"
    CUSTOMER = "customer"
    BUSINESS = "business"
    AGENT = "agent"
    KNOWLEDGE = "knowledge"


class MemoryRecord(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "memory_records"

    memory_type: Mapped[MemoryType] = mapped_column(Enum(MemoryType), index=True)
    # e.g. a customer id, conversation id, or agent name — null for
    # business-wide / knowledge-base entries that aren't tied to one subject.
    subject_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    content: Mapped[str] = mapped_column(Text)
    record_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    embedding: Mapped[list] = mapped_column(JSON, default=list)
