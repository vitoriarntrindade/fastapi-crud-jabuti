"""Cache key definitions and invalidation helpers for the users domain."""

import json
import logging
import uuid
from typing import Any

import redis.asyncio as aioredis

from app.core.config import get_settings
from app.core.exceptions import CacheError

logger = logging.getLogger(__name__)

_USER_KEY_PREFIX = "user"
_USER_LIST_KEY = "users:list"


def _user_key(user_id: uuid.UUID) -> str:
    return f"{_USER_KEY_PREFIX}:{user_id}"


class UserCache:
    """High-level cache operations for user data."""

    def __init__(self, client: aioredis.Redis) -> None:  # type: ignore[type-arg]
        self._client = client
        settings = get_settings()
        self._ttl = settings.cache_ttl_seconds
        self._list_ttl = settings.cache_list_ttl_seconds

    async def get_user(self, user_id: uuid.UUID) -> dict[str, Any] | None:
        """Retrieve a single cached user by ID.

        Args:
            user_id: The UUID of the user to retrieve.

        Returns:
            A dictionary with user data, or None on miss or error.
        """
        key = _user_key(user_id)
        try:
            raw = await self._client.get(key)
            if raw is None:
                logger.debug("Cache miss — key=%s", key)
                return None
            logger.debug("Cache hit — key=%s", key)
            return json.loads(raw)  # type: ignore[no-any-return]
        except Exception as exc:
            logger.warning("Cache read error (key=%s): %s", key, CacheError(exc))
            return None

    async def set_user(self, user_id: uuid.UUID, data: dict[str, Any]) -> None:
        """Store a user in the cache.

        Args:
            user_id: The UUID of the user.
            data: Serialisable user data dictionary.
        """
        key = _user_key(user_id)
        try:
            await self._client.setex(key, self._ttl, json.dumps(data, default=str))
            logger.debug("Cache set — key=%s ttl=%ds", key, self._ttl)
        except Exception as exc:
            logger.warning("Cache write error (key=%s): %s", key, CacheError(exc))

    async def get_user_list(self, page: int, page_size: int) -> dict[str, Any] | None:
        """Retrieve a cached paginated user list.

        Args:
            page: Page number.
            page_size: Number of items per page.

        Returns:
            A dictionary with paginated data, or None on miss or error.
        """
        key = f"{_USER_LIST_KEY}:page={page}:size={page_size}"
        try:
            raw = await self._client.get(key)
            if raw is None:
                logger.debug("Cache miss — key=%s", key)
                return None
            logger.debug("Cache hit — key=%s", key)
            return json.loads(raw)  # type: ignore[no-any-return]
        except Exception as exc:
            logger.warning("Cache read error (key=%s): %s", key, CacheError(exc))
            return None

    async def set_user_list(
        self, page: int, page_size: int, data: dict[str, Any]
    ) -> None:
        """Store a paginated user list in the cache.

        Args:
            page: Page number.
            page_size: Number of items per page.
            data: Serialisable paginated data dictionary.
        """
        key = f"{_USER_LIST_KEY}:page={page}:size={page_size}"
        try:
            await self._client.setex(key, self._list_ttl, json.dumps(data, default=str))
            logger.debug("Cache set — key=%s ttl=%ds", key, self._list_ttl)
        except Exception as exc:
            logger.warning("Cache write error (key=%s): %s", key, CacheError(exc))

    async def invalidate_user(self, user_id: uuid.UUID) -> None:
        """Delete the cached entry for a specific user and all list pages.

        Args:
            user_id: The UUID of the user whose cache should be cleared.
        """
        keys_to_delete = [_user_key(user_id)]
        try:
            pattern = f"{_USER_LIST_KEY}:*"
            async for key in self._client.scan_iter(pattern):
                keys_to_delete.append(key)
            if keys_to_delete:
                await self._client.delete(*keys_to_delete)
                logger.debug("Cache invalidated — keys=%s", keys_to_delete)
        except Exception as exc:
            logger.warning(
                "Cache invalidation error (user_id=%s): %s",
                user_id,
                CacheError(exc),
            )

    async def invalidate_user_lists(self) -> None:
        """Delete all cached paginated user list entries.

        Used after write operations that affect list results (e.g. create),
        without touching the per-user cache key.
        """
        try:
            pattern = f"{_USER_LIST_KEY}:*"
            list_keys: list[str] = []
            async for key in self._client.scan_iter(pattern):
                list_keys.append(key)
            if list_keys:
                await self._client.delete(*list_keys)
                logger.debug("Cache: list keys invalidated — keys=%s", list_keys)
        except Exception as exc:
            logger.warning("Cache list invalidation error: %s", CacheError(exc))
