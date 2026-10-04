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

    # Reserved for future providers — unused by OllamaProvider.
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    # --- Agent execution limits (spec Section 8 / 32: never allow
    # infinite agent loops) ---
    agent_max_iterations: int = 6
    agent_max_tool_calls: int = 10
    agent_tool_timeout_seconds: float = 30.0


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
