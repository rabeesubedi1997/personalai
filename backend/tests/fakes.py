"""Deterministic fake AIProvider for orchestrator/API tests — the real
Ollama integration is checked separately (manual live smoke test), not in
this automated suite."""
from __future__ import annotations

from collections.abc import Callable

from app.services.ai.base import AIProvider, ChatMessage, GenerationResult, ToolSpec


def _default_embed_fn(text: str) -> list[float]:
    """Deterministic, dependency-free stand-in embedding: two cheap hash-ish
    features. Tests that need meaningful similarity ranking should pass
    their own `embed_fn` instead (e.g. keyword-presence vectors)."""
    return [float(len(text) % 7), float(sum(ord(c) for c in text) % 13)]


class FakeAIProvider(AIProvider):
    """Returns `responses` in order, one per call to generate_with_tools/chat.
    If `responses` is exhausted, repeats the last one (useful for loop-limit
    tests that call forever)."""

    def __init__(
        self,
        responses: list[GenerationResult],
        embed_fn: Callable[[str], list[float]] | None = None,
    ):
        self.responses = responses
        self.call_count = 0
        self.embed_fn = embed_fn or _default_embed_fn
        # Records each call's messages, for tests that need to inspect what
        # was actually sent to the model (e.g. the prompt-injection wrapper).
        self.received_messages: list[list[ChatMessage]] = []

    def _next(self) -> GenerationResult:
        idx = min(self.call_count, len(self.responses) - 1)
        self.call_count += 1
        return self.responses[idx]

    async def generate(self, prompt: str, *, system: str | None = None) -> GenerationResult:
        return self._next()

    async def chat(self, messages: list[ChatMessage]) -> GenerationResult:
        return self._next()

    async def generate_with_tools(
        self, messages: list[ChatMessage], tools: list[ToolSpec]
    ) -> GenerationResult:
        self.received_messages.append(messages)
        return self._next()

    async def health_check(self) -> bool:
        return True

    async def embed(self, text: str) -> list[float]:
        return self.embed_fn(text)
