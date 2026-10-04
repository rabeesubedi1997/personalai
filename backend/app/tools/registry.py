"""
Central Tool Registry (spec Section 10).

The registry is the only place a tool name resolves to executable code.
Agents never get a live Tool object directly — they declare an
`allowed_tools` list of names, and the orchestrator asks the registry to
resolve + enforce that allow-list + run with a timeout. An agent requesting
a tool name that either doesn't exist or isn't in its own allow-list is a
hard refusal, not a soft warning.
"""
from __future__ import annotations

import asyncio
from functools import lru_cache

from app.core.logging import get_logger
from app.services.ai.base import ToolSpec
from app.tools.base import Tool, ToolExecutionError, ToolOutput

logger = get_logger(__name__)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def all_names(self) -> list[str]:
        return list(self._tools.keys())

    def specs_for(self, allowed_tool_names: list[str]) -> list[ToolSpec]:
        """Tool specs for only the names an agent is allowed to use —
        never hand the model the full registry (spec Section 9: agents
        must NOT have unrestricted access to all tools)."""
        specs = []
        for name in allowed_tool_names:
            tool = self._tools.get(name)
            if tool is not None:
                specs.append(tool.to_spec())
        return specs

    async def execute(
        self, name: str, arguments: dict, *, allowed_tool_names: list[str]
    ) -> ToolOutput:
        if name not in allowed_tool_names:
            logger.warning("tool_call_denied", tool=name, reason="not_in_agent_allowlist")
            raise ToolExecutionError(
                f"Tool '{name}' is not permitted for this agent."
            )
        tool = self._tools.get(name)
        if tool is None:
            logger.warning("tool_call_denied", tool=name, reason="unknown_tool")
            raise ToolExecutionError(f"Tool '{name}' does not exist.")

        try:
            return await asyncio.wait_for(
                tool.execute(**arguments), timeout=tool.timeout_seconds
            )
        except asyncio.TimeoutError as exc:
            logger.error("tool_call_timeout", tool=name, timeout=tool.timeout_seconds)
            raise ToolExecutionError(
                f"Tool '{name}' timed out after {tool.timeout_seconds}s."
            ) from exc
        except ToolExecutionError:
            raise
        except Exception as exc:  # defensive: a buggy tool must not crash the agent loop
            logger.error("tool_call_failed", tool=name, error=str(exc))
            raise ToolExecutionError(f"Tool '{name}' failed: {exc}") from exc


@lru_cache
def get_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    from app.tools.mock_tools import register_mock_tools

    register_mock_tools(registry)
    return registry
