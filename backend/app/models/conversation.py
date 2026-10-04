"""
Conversation thread storage — fixes the gap found live-testing Phase 6:
each POST /api/v1/agents/run call started a fresh context with no way to
continue a prior turn (e.g. a customer replying "yes, book it").

Deliberately NOT built on top of MemoryRecord/MemoryStore (Phase 4): that
system embeds every record for semantic search, which would mean an
embedding call on every single chat turn just to support sequential
replay — real latency cost for no benefit, since replay needs order, not
similarity. This is a separate, lighter-weight concern: an ordered log of
exactly what was exchanged, tenant-scoped like everything else.
"""
import uuid

from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ConversationMessage(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "conversation_messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(index=True)
    # Assigned sequentially by ConversationStore — authoritative ordering,
    # independent of timestamp resolution (SQLite timestamps can collide
    # for rapid successive inserts within one run).
    turn_index: Mapped[int] = mapped_column()
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text, default="")
    tool_call_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tool_calls: Mapped[list] = mapped_column(JSON, default=list)
