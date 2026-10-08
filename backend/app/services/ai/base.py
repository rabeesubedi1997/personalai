"""
Provider-agnostic AI interface (spec Section 3 / 38).

The rest of the application must depend only on `AIProvider` and call
`ai.generate(...)`, `ai.chat(...)`, `ai.generate_with_tools(...)` — never on
a concrete provider (Ollama/Claude/OpenAI) directly. This is what lets the
same orchestrator later run against a local model for simple work and a
hosted model for complex reasoning, per-agent, without touching call sites.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class ChatMessage:
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    # Present on role="tool" messages: which tool call this is a result for.
    tool_call_id: str | None = None
    # Present on role="assistant" messages that requested tool calls.
    tool_calls: list["ToolCall"] = field(default_factory=list)


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolResult:
    tool_call_id: str
    name: str
    content: str
    is_error: bool = False


@dataclass
class ToolSpec:
    """JSON-schema tool definition handed to the model, in the shape the
    Ollama/OpenAI-style function-calling API expects."""
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass
class GenerationResult:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: dict[str, Any] | None = None
    model: str = ""


@dataclass
class StreamChunk:
    """One item from `AIProvider.stream_with_tools`: either a piece of reply
    text (`text`) or, exactly once and last, the complete turn (`final`)."""

    text: str = ""
    final: GenerationResult | None = None


class AIProviderError(RuntimeError):
    """Raised when the underlying provider is unreachable or returns an
    error. Callers must surface this as a real failure (spec Section 47:
    "Never claim an action succeeded when it failed") rather than silently
    falling back to a fabricated response."""


class AIProvider(ABC):
    """Abstract base every concrete provider (Ollama, Claude, OpenAI, ...)
    implements. Application code depends on this type, never on a
    subclass."""

    @abstractmethod
    async def generate(self, prompt: str, *, system: str | None = None) -> GenerationResult:
        """Single-turn text generation."""

    @abstractmethod
    async def chat(self, messages: list[ChatMessage]) -> GenerationResult:
        """Multi-turn chat completion, no tool calling."""

    @abstractmethod
    async def generate_with_tools(
        self, messages: list[ChatMessage], tools: list[ToolSpec]
    ) -> GenerationResult:
        """Chat completion where the model may request tool calls. Callers
        (the orchestrator) are responsible for executing returned
        tool_calls and feeding ToolResults back in as role="tool"
        messages — this method does not execute tools itself."""

    # True only for providers whose stream_with_tools yields text as it is
    # generated. The default implementation below makes one blocking call,
    # so its "stream" is a single chunk — callers must not treat that as
    # live token delivery (the orchestrator holds such text back until it
    # knows the turn wasn't a half-formed tool call).
    streams_natively: bool = False

    async def stream_with_tools(
        self, messages: list[ChatMessage], tools: list[ToolSpec]
    ) -> AsyncIterator[StreamChunk]:
        """Like generate_with_tools, but yields reply text incrementally,
        then a final chunk carrying the full GenerationResult (including
        any tool_calls). Providers that can't stream inherit this fallback."""
        result = await self.generate_with_tools(messages, tools)
        if result.content:
            yield StreamChunk(text=result.content)
        yield StreamChunk(final=result)

    async def extract_json(
        self, messages: list[ChatMessage], schema: dict[str, Any]
    ) -> dict[str, Any]:
        """Read `messages` and return a JSON object matching `schema`
        (structured extraction — the model fills in fields, it does not chat).
        Providers that can't constrain output to a schema don't override this."""
        raise AIProviderError(f"{type(self).__name__} does not support structured extraction.")

    @abstractmethod
    async def health_check(self) -> bool:
        """Cheap reachability check used by /health."""

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Return an embedding vector for `text`, used by the memory system
        (app.memory.store) for similarity search. Implementations should
        use a small, fast embedding model — this is called on every memory
        write and every search query, not just occasionally."""
