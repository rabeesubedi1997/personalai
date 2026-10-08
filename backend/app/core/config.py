"""
Central application configuration.

All configuration comes from environment variables (see .env.example at the
repo root). Nothing here is hard-coded to a specific provider, model, or
secret — this module is the single place the rest of the app reads settings
from (`from app.core.config import settings`).
"""
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---
    app_env: Literal["development", "test", "production"] = "development"
    app_name: str = "PersonalOps AI"
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"

    # --- Database ---
    # Defaults to a local SQLite file so Phase 1 runs with zero extra
    # installs on a fresh machine. Point this at a PostgreSQL URL
    # (postgresql+asyncpg://...) for the spec's intended production target —
    # no code changes required, only this env var.
    database_url: str = "sqlite+aiosqlite:///./personalops.db"

    # --- Redis ---
    # Optional for Phase 1. If unset, caching/queue features degrade
    # gracefully (see app.core.redis_client) rather than failing startup.
    redis_url: str | None = "redis://localhost:6379/0"

    # --- Auth ---
    jwt_secret: str = Field(default="change-me-in-dev")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 8

    # --- AI Provider ---
    ai_provider: Literal["ollama", "claude", "openai"] = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b-instruct"
    ollama_embedding_model: str = "nomic-embed-text"
    ollama_request_timeout_seconds: float = 120.0
    # How long Ollama keeps the model resident with no requests. Below the
    # default 5m, a quiet gap (e.g. overnight) forces a full reload on top
    # of the cold prompt-eval cost of the next visitor's first message.
    ollama_keep_alive: str = "30m"
    # Bounds worst-case generation time per call — CPU inference is ~5-8
    # tok/s here, so an unbounded reply can add tens of seconds for no
    # benefit (customers don't need a 500-word answer to "is it available
    # Tuesday?"). Does not affect typical short replies.
    ollama_num_predict: int = 350

    # --- Prompt cache warmer (see app/services/ai/cache_warmer.py) ---
    # Ollama's prompt/KV cache for a given model holds only the most
    # recently processed prompt; the instant a different system+tools
    # prefix is processed (a different agent, or any other Ollama traffic),
    # the next request against this agent pays a full cold prompt-eval
    # again (measured ~20-25s for Tolemate's prompt on this CPU, vs ~0.2s
    # warm). Re-pinging the last-used agent's exact prefix during idle
    # gaps keeps it warm so a visitor's first message doesn't pay that
    # tax. Harmless no-op if disabled; never competes with a real request
    # (see cache_warmer.py for how it avoids overlapping with live calls).
    cache_warmer_enabled: bool = True
    cache_warmer_interval_seconds: float = 60.0

    # Reserved for future providers — unused by OllamaProvider.
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    # --- Website knowledge (see app/services/site_knowledge) ---
    # Every character of site content injected into a prompt is paid for in
    # CPU prompt-eval time (~30 tokens/s measured here, and it can't be
    # cached because it differs per question) — so retrieval is deliberately
    # tight: a few small chunks under a hard character budget, not a page dump.
    site_chunk_chars: int = 600
    site_rag_top_k: int = 3
    site_rag_max_chars: int = 1500
    # Minimum embedding similarity for a chunk to count as relevant at all
    # (below it the agent is told nothing matched rather than being fed a
    # weak, probably-irrelevant passage).
    site_rag_min_score: float = 0.45
    site_crawl_max_pages: int = 30
    site_crawl_timeout_seconds: float = 15.0

    # --- Agent execution limits (spec Section 8 / 32: never allow
    # infinite agent loops) ---
    agent_max_iterations: int = 6
    agent_max_tool_calls: int = 10
    agent_tool_timeout_seconds: float = 30.0

    # --- Proactive automation (spec Section 21) ---
    # tests/conftest.py sets SCHEDULER_ENABLED=false defensively; the ASGI
    # test client doesn't trigger app lifespan anyway, but this keeps the
    # intent explicit rather than relying on that incidentally.
    scheduler_enabled: bool = True
    scheduler_interval_seconds: float = 300.0
    approval_reminder_after_minutes: int = 15
    request_stale_after_hours: int = 24


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
