"""Background keep-warm pinger for Ollama's prompt/KV cache.

Measured live (see CHANGELOG): Ollama only holds the KV cache for the most
recently processed prompt per model. The instant a *different* system+tools
prefix is processed against the same model — a different agent, a different
tenant's conversation, even an unrelated health check — the next request
against this agent pays a full cold prompt-eval again. On this CPU that is
~20-25s for Tolemate's ~700-token system+tools prefix, versus ~0.2s warm.
Raising OLLAMA_NUM_PARALLEL did not avoid this for sequential (non-concurrent)
requests — confirmed by live A/B/C re-test — so the only lever that actually
keeps a quiet agent's cache warm is re-processing its exact prefix
periodically.

This loop re-sends the most-recently-active agent's exact prefix (built with
the identical construction AgentOrchestrator.run uses, so the prefix is
byte-for-byte the same and Ollama actually reuses it) with num_predict=1 —
cheap on the output side, since it's the input prompt processing we're
paying for on purpose, during idle time instead of while a visitor waits.

`mark_active(agent)` is called by AgentOrchestrator at the start of a real
run, so the warmer tracks whichever agent genuinely has traffic rather than
blindly cycling every registered business (which would just re-create the
same eviction problem between pings, as cycling multiple prefixes does).
"""
from __future__ import annotations

import asyncio

from app.agents.base_agent import BaseAgent
from app.core.config import settings
from app.core.logging import get_logger
from app.services.ai.base import AIProvider, AIProviderError, ChatMessage
from app.tools.registry import ToolRegistry

logger = get_logger(__name__)

# Set by AgentOrchestrator.run() on every real invocation; read by the
# warmer loop. A plain module-level variable is enough here — like the
# scheduler, this is a single in-process background loop, not shared
# across workers.
_last_active_agent: BaseAgent | None = None


def mark_active(agent: BaseAgent) -> None:
    global _last_active_agent
    _last_active_agent = agent


def build_warm_prefix(agent: BaseAgent, tool_registry: ToolRegistry) -> tuple[list[ChatMessage], list]:
    # Mirrors AgentOrchestrator.run's prefix construction exactly — a
    # mismatched prefix (even one extra character) misses the cache and
    # defeats the whole point.
    from app.orchestrator.engine import _ANTI_NARRATION_PREAMBLE

    tool_specs = tool_registry.specs_for(agent.allowed_tools)
    system_content = f"{_ANTI_NARRATION_PREAMBLE}\n\n{agent.system_prompt}"
    messages = [
        ChatMessage(role="system", content=system_content),
        ChatMessage(role="user", content="(cache warm-up ping — ignore)"),
    ]
    return messages, tool_specs


async def run_forever(ai_provider: AIProvider, tool_registry: ToolRegistry, interval_seconds: float) -> None:
    logger.info("cache_warmer_started", interval_seconds=interval_seconds)
    stop_event = asyncio.Event()
    while not stop_event.is_set():
        agent = _last_active_agent
        if agent is not None:
            try:
                messages, tool_specs = build_warm_prefix(agent, tool_registry)
                await ai_provider.generate_with_tools(messages, tool_specs)
                logger.info("cache_warmer_pinged", agent=agent.name)
            except AIProviderError as exc:
                # Ollama briefly unreachable, mid-restart, etc. — never
                # fatal to the loop, just skip this tick.
                logger.warning("cache_warmer_ping_failed", agent=agent.name, error=str(exc))
            except Exception as exc:  # a warmer bug must never take down the app
                logger.error("cache_warmer_unexpected_error", error=str(exc))
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            pass
