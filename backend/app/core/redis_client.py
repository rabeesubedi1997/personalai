"""
Redis client wrapper.

Redis is optional in Phase 1 (spec allows deferring non-core services on a
resource-constrained dev box). If REDIS_URL is unset or Redis is unreachable,
the app still starts; features that would use Redis (caching, rate limiting,
background job state — never permanent business data, per spec Section 28)
simply no-op with a logged warning instead of crashing the app.
"""
from __future__ import annotations

import redis.asyncio as redis

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_client: redis.Redis | None = None
_unavailable_warned = False


def get_redis() -> redis.Redis | None:
    global _client, _unavailable_warned
    if not settings.redis_url:
        return None
    if _client is None:
        try:
            _client = redis.from_url(settings.redis_url, decode_responses=True)
        except Exception:  # pragma: no cover - defensive
            if not _unavailable_warned:
                logger.warning("redis_client_init_failed", url=settings.redis_url)
                _unavailable_warned = True
            return None
    return _client


async def ping() -> bool:
    client = get_redis()
    if client is None:
        return False
    try:
        return bool(await client.ping())
    except Exception:
        return False
