"""
MemoryStore (spec Section 14): write and retrieve conversation/customer/
business/agent memory and knowledge-base entries, always tenant-scoped.

Similarity search is brute-force cosine similarity in Python over rows
already filtered by tenant (and optionally memory_type) — see the storage
note in app/models/memory.py for why, and what changes once Postgres +
pgvector is the target.
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import MemoryRecord, MemoryType
from app.services.ai.base import AIProvider


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


@dataclass
class ScoredMemory:
    record: MemoryRecord
    score: float


class MemoryStore:
    def __init__(self, ai_provider: AIProvider, db: AsyncSession) -> None:
        self.ai_provider = ai_provider
        self.db = db

    async def add(
        self,
        *,
        tenant_id: uuid.UUID,
        memory_type: MemoryType,
        content: str,
        subject_id: str | None = None,
        metadata: dict | None = None,
    ) -> MemoryRecord:
        embedding = await self.ai_provider.embed(content)
        record = MemoryRecord(
            tenant_id=tenant_id,
            memory_type=memory_type,
            subject_id=subject_id,
            content=content,
            record_metadata=metadata or {},
            embedding=embedding,
        )
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)
        return record

    async def list(
        self,
        *,
        tenant_id: uuid.UUID,
        memory_type: MemoryType | None = None,
        subject_id: str | None = None,
    ) -> list[MemoryRecord]:
        query = select(MemoryRecord).where(MemoryRecord.tenant_id == tenant_id)
        if memory_type is not None:
            query = query.where(MemoryRecord.memory_type == memory_type)
        if subject_id is not None:
            query = query.where(MemoryRecord.subject_id == subject_id)
        query = query.order_by(MemoryRecord.created_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def search(
        self,
        *,
        tenant_id: uuid.UUID,
        query: str,
        memory_type: MemoryType | None = None,
        top_k: int = 5,
    ) -> list[ScoredMemory]:
        candidates = await self.list(tenant_id=tenant_id, memory_type=memory_type)
        if not candidates:
            return []

        query_embedding = await self.ai_provider.embed(query)
        scored = [
            ScoredMemory(record=record, score=_cosine_similarity(query_embedding, record.embedding))
            for record in candidates
        ]
        scored.sort(key=lambda sm: sm.score, reverse=True)
        return scored[:top_k]
