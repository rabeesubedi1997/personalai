"""
Central Tool Registry (spec Section 10).

The registry is the only place a tool name resolves to executable code.
Agents never get a live Tool object directly — they declare an
`allowed_tools` list of names, and the orchestrator asks the registry to
resolve + enforce that allow-list + run with a timeout. An agent requesting
a tool name that either doesn't exist or isn't in its own allow-list is a
hard refusal, not a soft warning.

Phase 5 additions:
  - SENSITIVE/CRITICAL tools cannot be registered without
    `requires_approval = True` — this is a structural guarantee, not a
    convention someone can forget (spec Section 11/12).
  - Tool arguments are validated against the tool's own JSON schema before
    execution — malformed input from the model is rejected with a clear
    error rather than crashing the tool or running on bad data.
  - Denied calls (unauthorized/unknown tool) are written to the audit log,
    not just a structlog line — spec Section 25 requires this to be
    queryable, not just grep-able.
"""
from __future__ import annotations

import asyncio
from functools import lru_cache

import jsonschema

from app.core.logging import get_logger
from app.models.audit_log import AuditLog
from app.services.ai.base import ToolSpec
from app.tools.base import (
    ApprovalRequiredError,
    PermissionLevel,
    Tool,
    ToolContext,
    ToolExecutionError,
    ToolOutput,
)

logger = get_logger(__name__)

_APPROVAL_REQUIRED_LEVELS = {PermissionLevel.SENSITIVE, PermissionLevel.CRITICAL}


async def _audit(context: ToolContext, *, event_type: str, status: str, tool_name: str, detail: dict) -> None:
    entry = AuditLog(
        tenant_id=context.tenant_id,
        event_type=event_type,
        actor="agent",
        tool_name=tool_name,
        status=status,
        detail=detail,
    )
    context.db.add(entry)
    await context.db.commit()


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")
        if tool.permission_level in _APPROVAL_REQUIRED_LEVELS and not tool.requires_approval:
            raise ValueError(
                f"Tool '{tool.name}' has permission_level="
                f"'{tool.permission_level.value}' but requires_approval=False. "
                "SENSITIVE/CRITICAL tools must require human approval (spec "
                "Section 11/12) — set requires_approval=True."
            )
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
        self,
        name: str,
        arguments: dict,
        *,
        allowed_tool_names: list[str],
        context: ToolContext,
    ) -> ToolOutput:
        if name not in allowed_tool_names:
            logger.warning("tool_call_denied", tool=name, reason="not_in_agent_allowlist")
            await _audit(
                context,
                event_type="tool_call_denied",
                status="denied",
                tool_name=name,
                detail={"reason": "not_in_agent_allowlist", "arguments": arguments},
            )
            raise ToolExecutionError(
                f"Tool '{name}' is not permitted for this agent."
            )
        tool = self._tools.get(name)
        if tool is None:
            logger.warning("tool_call_denied", tool=name, reason="unknown_tool")
            await _audit(
                context,
                event_type="tool_call_denied",
                status="denied",
                tool_name=name,
                detail={"reason": "unknown_tool", "arguments": arguments},
            )
            raise ToolExecutionError(f"Tool '{name}' does not exist.")

        try:
            jsonschema.validate(instance=arguments, schema=tool.parameters)
        except jsonschema.ValidationError as exc:
            logger.warning("tool_call_invalid_arguments", tool=name, error=exc.message)
            raise ToolExecutionError(
                f"Invalid arguments for tool '{name}': {exc.message}"
            ) from exc

        if tool.requires_approval:
            raise ApprovalRequiredError(name, arguments)

        try:
            return await asyncio.wait_for(
                tool.execute(context, **arguments), timeout=tool.timeout_seconds
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
    from app.connectors import all_business_tools
    from app.tools.memory_tools import register_memory_tools
    from app.tools.mock_tools import register_mock_tools

    register_mock_tools(registry)
    register_memory_tools(registry)
    for tool in all_business_tools():
        registry.register(tool)
    return registry
