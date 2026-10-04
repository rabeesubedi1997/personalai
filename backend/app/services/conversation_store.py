"""ConversationStore: load/append an ordered, tenant-scoped thread of
ChatMessages, so AgentOrchestrator.run() can be given prior turns and
POST /api/v1/agents/run can support continuing a conversation via
conversation_id."""
from __future__ import annotations

import dataclasses
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import ConversationMessage
from app.services.ai.base import ChatMessage, ToolCall


class ConversationStore:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def load(self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID) -> list[ChatMessage]:
        result = await self.db.execute(
            select(ConversationMessage)
            .where(
                ConversationMessage.tenant_id == tenant_id,
                ConversationMessage.conversation_id == conversation_id,
            )
            .order_by(ConversationMessage.turn_index)
        )
        rows = result.scalars().all()
        return [
            ChatMessage(
                role=row.role,
                content=row.content,
                tool_call_id=row.tool_call_id,
                tool_calls=[ToolCall(**tc) for tc in row.tool_calls],
            )
            for row in rows
        ]

    async def append(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        messages: list[ChatMessage],
    ) -> None:
        if not messages:
            return
        count_result = await self.db.execute(
            select(func.count())
            .select_from(ConversationMessage)
            .where(
                ConversationMessage.tenant_id == tenant_id,
                ConversationMessage.conversation_id == conversation_id,
            )
        )
        start_index = count_result.scalar_one()
        for offset, msg in enumerate(messages):
            self.db.add(
                ConversationMessage(
                    tenant_id=tenant_id,
                    conversation_id=conversation_id,
                    turn_index=start_index + offset,
                    role=msg.role,
                    content=msg.content,
                    tool_call_id=msg.tool_call_id,
                    tool_calls=[dataclasses.asdict(tc) for tc in msg.tool_calls],
                )
            )
        await self.db.commit()
