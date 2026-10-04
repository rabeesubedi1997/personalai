"""Deterministic fake AIProvider for orchestrator/API tests — the real
Ollama integration is checked separately (manual live smoke test), not in
this automated suite."""
from __future__ import annotations

from app.services.ai.base import AIProvider, ChatMessage, GenerationResult, ToolSpec


class FakeAIProvider(AIProvider):
    """Returns `responses` in order, one per call to generate_with_tools/chat.
    If `responses` is exhausted, repeats the last one (useful for loop-limit
    tests that call forever)."""

    def __init__(self, responses: list[GenerationResult]):
        self.responses = responses
        self.call_count = 0

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
        return self._next()

    async def health_check(self) -> bool:
        return True
