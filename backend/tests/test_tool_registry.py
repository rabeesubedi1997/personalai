import pytest

from app.tools.base import ToolExecutionError
from app.tools.registry import get_tool_registry

pytestmark = pytest.mark.asyncio


async def test_execute_allowed_tool_succeeds():
    registry = get_tool_registry()
    output = await registry.execute(
        "get_current_time", {}, allowed_tool_names=["get_current_time"]
    )
    assert "T" in output.content  # ISO timestamp


async def test_execute_denies_tool_not_in_allowlist():
    registry = get_tool_registry()
    with pytest.raises(ToolExecutionError):
        await registry.execute(
            "get_current_time", {}, allowed_tool_names=["search_knowledge_base"]
        )


async def test_execute_denies_unknown_tool():
    registry = get_tool_registry()
    with pytest.raises(ToolExecutionError):
        await registry.execute(
            "not_a_real_tool", {}, allowed_tool_names=["not_a_real_tool"]
        )


async def test_create_task_rejects_empty_title():
    registry = get_tool_registry()
    with pytest.raises(ToolExecutionError):
        await registry.execute(
            "create_task", {"title": "  "}, allowed_tool_names=["create_task"]
        )


async def test_search_knowledge_base_returns_match():
    registry = get_tool_registry()
    output = await registry.execute(
        "search_knowledge_base",
        {"query": "what are your hours"},
        allowed_tool_names=["search_knowledge_base"],
    )
    assert "24/7" in output.content
