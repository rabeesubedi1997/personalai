"""
Mock tools for the Phase 2 demonstration agent (spec: "Use mock tools
initially"). These stand in for what will become real connector-backed
tools from Phase 6 onward — the shape (name/schema/permission) is the real
contract; the implementation underneath is what changes later.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.tools.base import PermissionLevel, Tool, ToolExecutionError, ToolOutput


class GetCurrentTimeTool(Tool):
    name = "get_current_time"
    description = "Get the current UTC date and time."
    parameters: dict[str, Any] = {"type": "object", "properties": {}}
    permission_level = PermissionLevel.READ
    timeout_seconds = 5.0

    async def execute(self, **kwargs: Any) -> ToolOutput:
        now = datetime.now(timezone.utc).isoformat()
        return ToolOutput(content=now, data={"utc_time": now})


class SearchKnowledgeBaseTool(Tool):
    """Mock stand-in for a future pgvector-backed knowledge base search
    (Phase 4) — same name/shape, real implementation later."""

    name = "search_knowledge_base"
    description = "Search PersonalOps AI's internal knowledge base for an answer to a question."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "The search query"}},
        "required": ["query"],
    }
    permission_level = PermissionLevel.READ
    timeout_seconds = 10.0

    _FAKE_DOCS = {
        "hours": "PersonalOps AI support is available 24/7 via the agent platform.",
        "pricing": "Pricing is not yet public; this is a pre-launch development build.",
    }

    async def execute(self, query: str, **kwargs: Any) -> ToolOutput:
        query_lower = query.lower()
        for keyword, answer in self._FAKE_DOCS.items():
            if keyword in query_lower:
                return ToolOutput(content=answer, data={"matched": keyword})
        return ToolOutput(
            content="No matching document found in the knowledge base.",
            data={"matched": None},
        )


class CreateTaskTool(Tool):
    """Mock stand-in for a future real task/CRM write. SAFE_WRITE level:
    non-destructive, no approval required, but still a write — logged like
    every tool call."""

    name = "create_task"
    description = "Create an internal follow-up task."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {"title": {"type": "string"}},
        "required": ["title"],
    }
    permission_level = PermissionLevel.SAFE_WRITE
    timeout_seconds = 10.0

    async def execute(self, title: str, **kwargs: Any) -> ToolOutput:
        if not title or not title.strip():
            raise ToolExecutionError("Task title must not be empty.")
        task_id = str(uuid.uuid4())
        return ToolOutput(
            content=f"Created task '{title}' (id={task_id}).",
            data={"task_id": task_id, "title": title},
        )


def register_mock_tools(registry) -> None:
    registry.register(GetCurrentTimeTool())
    registry.register(SearchKnowledgeBaseTool())
    registry.register(CreateTaskTool())
