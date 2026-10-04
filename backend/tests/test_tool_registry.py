import uuid

import pytest

from app.memory.store import MemoryStore
from app.models.memory import MemoryType
from app.tools.base import (
    ApprovalRequiredError,
    PermissionLevel,
    Tool,
    ToolContext,
    ToolExecutionError,
    ToolOutput,
)
from app.tools.registry import ToolRegistry, get_tool_registry
from tests.fakes import FakeAIProvider

pytestmark = pytest.mark.asyncio


@pytest.fixture
def context(db_session):
    return ToolContext(
        tenant_id=uuid.uuid4(), db=db_session, ai_provider=FakeAIProvider(responses=[])
    )


async def test_execute_allowed_tool_succeeds(context):
    registry = get_tool_registry()
    output = await registry.execute(
        "get_current_time", {}, allowed_tool_names=["get_current_time"], context=context
    )
    assert "T" in output.content  # ISO timestamp


async def test_execute_denies_tool_not_in_allowlist(context):
    registry = get_tool_registry()
    with pytest.raises(ToolExecutionError):
        await registry.execute(
            "get_current_time",
            {},
            allowed_tool_names=["search_knowledge_base"],
            context=context,
        )


async def test_execute_denies_unknown_tool(context):
    registry = get_tool_registry()
    with pytest.raises(ToolExecutionError):
        await registry.execute(
            "not_a_real_tool", {}, allowed_tool_names=["not_a_real_tool"], context=context
        )


async def test_create_task_rejects_empty_title(context):
    registry = get_tool_registry()
    with pytest.raises(ToolExecutionError):
        await registry.execute(
            "create_task", {"title": "  "}, allowed_tool_names=["create_task"], context=context
        )


async def test_search_knowledge_base_returns_real_memory_match(context):
    # search_knowledge_base is now memory-backed (Phase 4) — seed a real
    # memory record first, through the same MemoryStore the tool uses.
    store = MemoryStore(context.ai_provider, context.db)
    await store.add(
        tenant_id=context.tenant_id,
        memory_type=MemoryType.KNOWLEDGE,
        content="PersonalOps AI support is available 24/7.",
    )

    registry = get_tool_registry()
    output = await registry.execute(
        "search_knowledge_base",
        {"query": "support hours"},
        allowed_tool_names=["search_knowledge_base"],
        context=context,
    )
    assert "24/7" in output.content


async def test_sensitive_tool_raises_approval_required_without_executing(context):
    registry = get_tool_registry()
    with pytest.raises(ApprovalRequiredError) as exc_info:
        await registry.execute(
            "cancel_booking",
            {"booking_id": "BK-42"},
            allowed_tool_names=["cancel_booking"],
            context=context,
        )
    assert exc_info.value.tool_name == "cancel_booking"
    assert exc_info.value.arguments == {"booking_id": "BK-42"}


async def test_invalid_tool_arguments_rejected_by_schema(context):
    registry = get_tool_registry()
    with pytest.raises(ToolExecutionError):
        # missing required "title"
        await registry.execute(
            "create_task", {}, allowed_tool_names=["create_task"], context=context
        )


async def test_registering_sensitive_tool_without_approval_is_rejected():
    class _UnsafeSensitiveTool(Tool):
        name = "unsafe_sensitive_tool"
        description = "A sensitive tool that forgot requires_approval."
        parameters = {"type": "object", "properties": {}}
        permission_level = PermissionLevel.SENSITIVE
        requires_approval = False  # the bug this test catches

        async def execute(self, context, **kwargs):
            return ToolOutput(content="should never run")

    registry = ToolRegistry()
    with pytest.raises(ValueError, match="requires_approval"):
        registry.register(_UnsafeSensitiveTool())


async def test_search_knowledge_base_reports_no_match_honestly(context):
    # No memory seeded at all for this tenant — must say unavailable, not
    # fabricate (spec Section 47/48).
    registry = get_tool_registry()
    output = await registry.execute(
        "search_knowledge_base",
        {"query": "anything at all"},
        allowed_tool_names=["search_knowledge_base"],
        context=context,
    )
    assert output.data == {"matched": None}
    assert "no matching document" in output.content.lower()
