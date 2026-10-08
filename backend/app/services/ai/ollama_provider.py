"""
Ollama implementation of AIProvider, talking to the local Ollama HTTP API
(default http://localhost:11434). Configured entirely via OLLAMA_BASE_URL /
OLLAMA_MODEL env vars — no model name is hard-coded here.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.services.ai.base import (
    AIProvider,
    AIProviderError,
    ChatMessage,
    GenerationResult,
    StreamChunk,
    ToolCall,
    ToolSpec,
)

logger = get_logger(__name__)

# Qwen's chat template renders a literal "<tool_call>" tag as part of how
# Ollama recognizes and parses out a REAL structured tool call — stopping
# generation there (tried first) breaks tool-calling entirely, since Ollama
# never gets to see the JSON that was going to follow it. The actual, safe
# fix is narrower: only stop a hallucinated continuation of the
# conversation into a fake next turn (seen in practice as a literal
# "<|im_start|>" appearing in content once the model has already finished
# its own turn). This leaves real tool-call rendering untouched.
_RUNAWAY_STOP_SEQUENCES = ["<|im_start|>"]


def _chat_options() -> dict[str, Any]:
    return {"stop": _RUNAWAY_STOP_SEQUENCES, "num_predict": settings.ollama_num_predict}


def _message_to_dict(msg: ChatMessage) -> dict[str, Any]:
    d: dict[str, Any] = {"role": msg.role, "content": msg.content}
    if msg.tool_call_id:
        d["tool_call_id"] = msg.tool_call_id
    return d


def _tool_spec_to_dict(tool: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


def _parse_tool_calls(message: dict[str, Any], id_offset: int = 0) -> list[ToolCall]:
    tool_calls: list[ToolCall] = []
    for i, raw_call in enumerate(message.get("tool_calls", []) or []):
        fn = raw_call.get("function", {})
        raw_args = fn.get("arguments", {})
        # Ollama normally returns parsed-object arguments already; be
        # defensive in case a given model emits a JSON string instead.
        if isinstance(raw_args, str):
            try:
                raw_args = json.loads(raw_args)
            except json.JSONDecodeError:
                raw_args = {}
        tool_calls.append(
            ToolCall(id=str(raw_call.get("id", i + id_offset)), name=fn.get("name", ""), arguments=raw_args)
        )
    return tool_calls


class OllamaProvider(AIProvider):
    streams_natively = True

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.ollama_model
        self.timeout = timeout or settings.ollama_request_timeout_seconds

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            logger.error("ollama_request_failed", url=url, error=str(exc))
            raise AIProviderError(f"Ollama request to {path} failed: {exc}") from exc

    async def generate(self, prompt: str, *, system: str | None = None) -> GenerationResult:
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": settings.ollama_keep_alive,
        }
        if system:
            payload["system"] = system
        data = await self._post("/api/generate", payload)
        return GenerationResult(
            content=data.get("response", ""), raw=data, model=self.model
        )

    async def chat(self, messages: list[ChatMessage]) -> GenerationResult:
        payload = {
            "model": self.model,
            "messages": [_message_to_dict(m) for m in messages],
            "stream": False,
            "options": _chat_options(),
            "keep_alive": settings.ollama_keep_alive,
        }
        data = await self._post("/api/chat", payload)
        message = data.get("message", {})
        return GenerationResult(
            content=message.get("content", ""), raw=data, model=self.model
        )

    async def generate_with_tools(
        self, messages: list[ChatMessage], tools: list[ToolSpec]
    ) -> GenerationResult:
        payload = {
            "model": self.model,
            "messages": [_message_to_dict(m) for m in messages],
            "tools": [_tool_spec_to_dict(t) for t in tools],
            "stream": False,
            "options": _chat_options(),
            "keep_alive": settings.ollama_keep_alive,
        }
        data = await self._post("/api/chat", payload)
        message = data.get("message", {})

        tool_calls = _parse_tool_calls(message)

        return GenerationResult(
            content=message.get("content", ""),
            tool_calls=tool_calls,
            raw=data,
            model=self.model,
        )

    async def stream_with_tools(
        self, messages: list[ChatMessage], tools: list[ToolSpec]
    ) -> AsyncIterator[StreamChunk]:
        """Same request as generate_with_tools but with stream=true: Ollama
        sends newline-delimited JSON, reply text arrives token by token and
        any tool call arrives as its own chunk (verified on Ollama 0.5.7)."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [_message_to_dict(m) for m in messages],
            "stream": True,
            "options": _chat_options(),
            "keep_alive": settings.ollama_keep_alive,
        }
        if tools:
            payload["tools"] = [_tool_spec_to_dict(t) for t in tools]

        url = f"{self.base_url}/api/chat"
        content_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", url, json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        data = json.loads(line)
                        message = data.get("message", {})
                        text = message.get("content", "")
                        if text:
                            content_parts.append(text)
                            yield StreamChunk(text=text)
                        tool_calls.extend(_parse_tool_calls(message, len(tool_calls)))
                        if data.get("done"):
                            break
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            logger.error("ollama_stream_failed", url=url, error=str(exc))
            raise AIProviderError(f"Ollama streaming request failed: {exc}") from exc

        yield StreamChunk(
            final=GenerationResult(
                content="".join(content_parts), tool_calls=tool_calls, model=self.model
            )
        )

    async def extract_json(
        self, messages: list[ChatMessage], schema: dict[str, Any]
    ) -> dict[str, Any]:
        """Structured extraction: Ollama constrains the output to `schema`, so a
        small model fills fields in rather than free-chatting. Temperature 0 and
        a short cap — this is reading, not writing."""
        payload = {
            "model": self.model,
            "messages": [_message_to_dict(m) for m in messages],
            "stream": False,
            "format": schema,
            "options": {"temperature": 0, "num_predict": 200},
            "keep_alive": settings.ollama_keep_alive,
        }
        data = await self._post("/api/chat", payload)
        content = data.get("message", {}).get("content", "")
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise AIProviderError(f"Ollama returned invalid JSON for extraction: {content[:200]!r}") from exc
        if not isinstance(parsed, dict):
            raise AIProviderError("Ollama extraction did not return a JSON object.")
        return parsed

    async def health_check(self) -> bool:
        # This backs GET /api/v1/health, which the dashboard calls on every
        # page load — a liveness ping should feel instant even if Ollama is
        # momentarily busy (e.g. mid-inference on another request), so this
        # uses a short timeout distinct from ollama_request_timeout_seconds
        # (which governs actual generate/chat calls and needs to be long).
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(f"{self.base_url}/api/version")
                return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def embed(self, text: str) -> list[float]:
        data = await self._post(
            "/api/embeddings",
            {"model": settings.ollama_embedding_model, "prompt": text},
        )
        embedding = data.get("embedding")
        if not embedding:
            raise AIProviderError("Ollama returned no embedding for the given text.")
        return embedding
