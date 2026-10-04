"""
Redis client wrapper.

Redis is optional in Phase 1 (spec allows deferring non-core services on a
resource-constrained dev box). If REDIS_URL is unset or Redis is unreachable,
the app still starts; features that would use Redis (caching, rate limiting,
background job state — never permanent business data, per spec Section 28)
simply no-op with a logged warning instead of crashing the app.

A real bug lived here: with no explicit socket timeout, connecting to an
unreachable "localhost:6379" (Redis simply not running — our own documented
default dev state) took ~4 seconds to fail, because Windows tries IPv6
first and falls back to IPv4 only after that attempt times out. Since
`ping()` backs GET /api/v1/health, which the dashboard calls on every page
load, this made "graceful degradation" technically correct but
practically painful — a 4+ second wait on every health check just to
confirm Redis isn't there, something already known and expected. Short,
explicit timeouts below (and a hard `asyncio.wait_for` cap as a
belt-and-suspenders bound regardless of the client's own settings) make
the unavailable case fail fast instead.
"""
from __future__ import annotations

import asyncio

import redis.asyncio as redis

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_client: redis.Redis | None = None
_unavailable_warned = False

_CONNECT_TIMEOUT_SECONDS = 1.0


def get_redis() -> redis.Redis | None:
    global _client, _unavailable_warned
    if not settings.redis_url:
        return None
    if _client is None:
        try:
            _client = redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=_CONNECT_TIMEOUT_SECONDS,
                socket_timeout=_CONNECT_TIMEOUT_SECONDS,
            )
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
        return bool(await asyncio.wait_for(client.ping(), timeout=_CONNECT_TIMEOUT_SECONDS + 0.5))
    except Exception:
        return False
