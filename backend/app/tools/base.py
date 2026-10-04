"""
Tool base class (spec Section 10/11).

Tools are the ONLY thing an agent/LLM can act through. There is no path
from a tool to raw SQL, the shell, the filesystem, or a production
database — a tool is a narrow, schema-validated, named operation, and every
tool declares its own permission level up front.
"""
from __future__ import annotations

import enum
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.services.ai.base import AIProvider, ToolSpec

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class PermissionLevel(str, enum.Enum):
    """Spec Section 11. Ordered low -> high risk."""

    READ = "read"
    SAFE_WRITE = "safe_write"
    SENSITIVE = "sensitive"
    CRITICAL = "critical"


class ToolExecutionError(RuntimeError):
    """Raised by a tool's execute() on failure. The orchestrator turns this
    into a tool-result message with is_error=True rather than letting it
    crash the agent loop or silently appear as success."""


@dataclass
class ToolOutput:
    content: str
    data: dict[str, Any] | None = None


@dataclass
class ToolContext:
    """Request-scoped dependencies a tool may need — tenant isolation,
    DB access, and the AI provider (e.g. for embeddings). Built once per
    agent run by the API layer (app/api/v1/agents.py) and threaded through
    AgentOrchestrator -> ToolRegistry -> Tool.execute(). A tool that doesn't
    need any of this (e.g. get_current_time) just ignores it."""

    tenant_id: uuid.UUID
    db: "AsyncSession"
    ai_provider: AIProvider


class Tool(ABC):
    name: str
    description: str
    parameters: dict[str, Any]
    permission_level: PermissionLevel = PermissionLevel.READ
    requires_approval: bool = False
    timeout_seconds: float = 15.0

    @abstractmethod
    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolOutput:
        """Run the tool. Must raise ToolExecutionError on failure rather
        than returning a result that looks successful (spec Section 47:
        never claim success when an action failed)."""

    def to_spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name, description=self.description, parameters=self.parameters
        )
