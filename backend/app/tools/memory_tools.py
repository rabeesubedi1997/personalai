"""
Memory-backed tools — the real (not mock) implementation of
`search_knowledge_base`, graduated from Phase 2's hardcoded dict to
Phase 4's `MemoryStore` (see app/tools/mock_tools.py for the history).

This tool only ever returns what's actually stored in the tenant's
`knowledge`-type memory records (added via POST /api/v1/memory) — it never
invents an answer, matching spec Section 47/48. If nothing in memory is
similar enough to the query, it says so plainly rather than returning a
weak, probably-irrelevant match.
"""
from __future__ import annotations

from typing import Any

from app.memory.store import MemoryStore
from app.models.memory import MemoryType
from app.tools.base import PermissionLevel, Tool, ToolContext, ToolOutput

# Below this cosine-similarity score, a match is treated as "no relevant
# document" rather than a weak guess. Tuned empirically against
# nomic-embed-text (see CHANGELOG for the live verification that set this).
MATCH_THRESHOLD = 0.55


class SearchKnowledgeBaseTool(Tool):
    name = "search_knowledge_base"
    description = (
        "Search the tenant's knowledge base for an answer to a factual "
        "question (hours, policies, pricing, availability, etc). Returns "
        "the best-matching stored document, or says no match was found."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "The search query"}},
        "required": ["query"],
    }
    permission_level = PermissionLevel.READ
    timeout_seconds = 15.0

    async def execute(self, context: ToolContext, query: str, **kwargs: Any) -> ToolOutput:
        store = MemoryStore(context.ai_provider, context.db)
        results = await store.search(
            tenant_id=context.tenant_id,
            query=query,
            memory_type=MemoryType.KNOWLEDGE,
            top_k=1,
        )
        if not results or results[0].score < MATCH_THRESHOLD:
            return ToolOutput(
                content="No matching document found in the knowledge base.",
                data={"matched": None},
            )
        top = results[0]
        return ToolOutput(
            content=top.record.content,
            data={"matched_id": str(top.record.id), "score": top.score},
        )


def register_memory_tools(registry) -> None:
    registry.register(SearchKnowledgeBaseTool())
