"""Provider factory — the one place AI_PROVIDER is switched on. Everything
else in the app calls get_ai_provider() and depends only on AIProvider."""
from functools import lru_cache

from app.core.config import settings
from app.services.ai.base import AIProvider


@lru_cache
def get_ai_provider() -> AIProvider:
    if settings.ai_provider == "ollama":
        from app.services.ai.ollama_provider import OllamaProvider

        return OllamaProvider()
    if settings.ai_provider == "claude":
        raise NotImplementedError(
            "ClaudeProvider is not implemented yet. Set AI_PROVIDER=ollama for now."
        )
    if settings.ai_provider == "openai":
        raise NotImplementedError(
            "OpenAIProvider is not implemented yet. Set AI_PROVIDER=ollama for now."
        )
    raise ValueError(f"Unknown AI_PROVIDER: {settings.ai_provider}")
