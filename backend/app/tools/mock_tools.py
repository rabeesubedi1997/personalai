"""
Mock tools for the Phase 2 demonstration agent (spec: "Use mock tools
initially"). These stand in for what will become real connector-backed
tools from Phase 6 onward — the shape (name/schema/permission) is the real
contract; the implementation underneath is what changes later.

Note: `search_knowledge_base` used to live here as a hardcoded-dict mock.
As of Phase 4 it's been graduated to a real memory-backed implementation
(see app/tools/memory_tools.py) — same tool name and contract, real data
underneath. `get_current_time` and `create_task` remain mocks; neither has
a real backing system yet.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.tools.base import PermissionLevel, Tool, ToolContext, ToolExecutionError, ToolOutput


class GetCurrentTimeTool(Tool):
    name = "get_current_time"
    description = "Get the current UTC date and time."
    parameters: dict[str, Any] = {"type": "object", "properties": {}}
    permission_level = PermissionLevel.READ
    timeout_seconds = 5.0

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolOutput:
        now = datetime.now(timezone.utc).isoformat()
        return ToolOutput(content=now, data={"utc_time": now})


class CancelBookingTool(Tool):
    """
    Generic, business-agnostic 'cancel a booking' capability — deliberately
    not Tolemate/GharNepal/ParadiseNepal-specific. Any future business agent
    that manages bookings (a Tolemate service booking, a Ghar Nepal viewing
    appointment, a Paradise Nepal production booking) can use this same
    tool contract once a real connector backs it (Phase 6+); only the
    connector underneath changes, not the tool shape or the approval gate.

    SENSITIVE: cancelling a booking affects a real customer commitment, so
    this requires human approval before executing (spec Section 11/12) —
    the registry enforces that structurally, not just by convention.
    """

    name = "cancel_booking"
    description = (
        "Cancel an existing booking by its id. Requires human approval "
        "before it takes effect."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "booking_id": {"type": "string", "description": "The booking to cancel"},
            "reason": {"type": "string", "description": "Why it's being cancelled"},
        },
        "required": ["booking_id"],
    }
    permission_level = PermissionLevel.SENSITIVE
    requires_approval = True
    timeout_seconds = 10.0

    async def execute(
        self, context: ToolContext, booking_id: str, reason: str = "", **kwargs: Any
    ) -> ToolOutput:
        if not booking_id or not booking_id.strip():
            raise ToolExecutionError("booking_id must not be empty.")
        # Mock: no real booking system exists yet (Phase 6+ connector work).
        # Once a real connector exists, this calls it instead; the tool
        # contract and the approval gate above do not change.
        return ToolOutput(
            content=f"Booking '{booking_id}' has been cancelled.",
            data={"booking_id": booking_id, "reason": reason, "cancelled": True},
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

    async def execute(self, context: ToolContext, title: str, **kwargs: Any) -> ToolOutput:
        if not title or not title.strip():
            raise ToolExecutionError("Task title must not be empty.")
        task_id = str(uuid.uuid4())
        return ToolOutput(
            content=f"Created task '{title}' (id={task_id}).",
            data={"task_id": task_id, "title": title},
        )


def register_mock_tools(registry) -> None:
    registry.register(GetCurrentTimeTool())
    registry.register(CreateTaskTool())
    registry.register(CancelBookingTool())
