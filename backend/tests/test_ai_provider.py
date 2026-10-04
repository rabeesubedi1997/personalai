"""
Tests for the AIProvider abstraction. These use a stub/mock HTTP transport
so the test suite does not depend on Ollama actually running — a real,
live smoke test against the running Ollama + Qwen model is done separately
via the /api/v1/ai/smoke-test endpoint (manual/integration check, not CI).
"""
import httpx
import pytest

from app.services.ai.base import ChatMessage, ToolSpec
from app.services.ai.ollama_provider import OllamaProvider

pytestmark = pytest.mark.asyncio


class _MockTransport(httpx.AsyncBaseTransport):
    def __init__(self, handler):
        self.handler = handler

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return self.handler(request)


async def _patched_post(monkeypatch, json_response: dict):
    async def fake_post(self, path, payload):
        return json_response

    monkeypatch.setattr(OllamaProvider, "_post", fake_post)


async def test_chat_returns_content(monkeypatch):
    await _patched_post(
        monkeypatch, {"message": {"role": "assistant", "content": "pong"}}
    )
    provider = OllamaProvider()
    result = await provider.chat([ChatMessage(role="user", content="ping")])
    assert result.content == "pong"


async def test_generate_with_tools_parses_tool_calls(monkeypatch):
    await _patched_post(
        monkeypatch,
        {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {
                            "name": "search_property",
                            "arguments": {"location": "Lalitpur"},
                        },
                    }
                ],
            }
        },
    )
    provider = OllamaProvider()
    tool = ToolSpec(
        name="search_property",
        description="Search properties",
        parameters={"type": "object", "properties": {"location": {"type": "string"}}},
    )
    result = await provider.generate_with_tools(
        [ChatMessage(role="user", content="find a house in Lalitpur")], [tool]
    )
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "search_property"
    assert result.tool_calls[0].arguments == {"location": "Lalitpur"}


async def test_health_check_false_when_unreachable():
    provider = OllamaProvider(base_url="http://localhost:1")
    assert await provider.health_check() is False
