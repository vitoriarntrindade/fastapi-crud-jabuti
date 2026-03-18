"""Redis client factory and lifecycle management."""

import logging

import redis.asyncio as aioredis

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_redis_client: aioredis.Redis | None = None  # type: ignore[type-arg]


async def get_redis_client() -> aioredis.Redis:  # type: ignore[type-arg]
    """Return the shared async Redis client, creating it on first call."""
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        logger.info("Redis client initialised at %s", settings.redis_url)
    return _redis_client


async def close_redis_client() -> None:
    """Close the shared Redis client gracefully."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()  # type: ignore[attr-defined]
        _redis_client = None
        logger.info("Redis client closed")
