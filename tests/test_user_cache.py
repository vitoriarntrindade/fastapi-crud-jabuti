"""Tests for UserCache — cache read, write, and invalidation logic."""

import json
import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.cache.user_cache import UserCache

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _async_iter(items: list[Any]) -> AsyncGenerator[Any, None]:
    """Yield items one by one as an async generator."""
    for item in items:
        yield item


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_redis() -> MagicMock:
    """Return a Redis client mock with sensible async defaults."""
    client = MagicMock()
    client.get = AsyncMock(return_value=None)
    client.setex = AsyncMock(return_value=True)
    client.delete = AsyncMock(return_value=1)
    client.scan_iter = MagicMock(return_value=_async_iter([]))
    return client


@pytest.fixture
def cache(mock_redis: MagicMock) -> UserCache:
    """Return a UserCache wired with the mock Redis client."""
    return UserCache(client=mock_redis)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGetUser:
    async def test_returns_none_on_cache_miss(self, cache: UserCache) -> None:
        # mock_redis.get already returns None by default (fixture)
        result = await cache.get_user(uuid.uuid4())

        assert result is None

    async def test_returns_parsed_dict_on_cache_hit(
        self, cache: UserCache, mock_redis: MagicMock
    ) -> None:
        # Arrange
        user_id = uuid.uuid4()
        data = {"id": str(user_id), "name": "Alice", "email": "a@a.com", "age": 30}
        mock_redis.get.return_value = json.dumps(data)

        # Act
        result = await cache.get_user(user_id)

        # Assert
        assert result == data

    async def test_returns_none_on_redis_error(
        self, cache: UserCache, mock_redis: MagicMock
    ) -> None:
        # Arrange
        mock_redis.get.side_effect = Exception("Redis is down")

        # Act
        result = await cache.get_user(uuid.uuid4())

        # Assert — cache errors must never propagate
        assert result is None


class TestSetUser:
    async def test_stores_serialised_data_under_user_key(
        self, cache: UserCache, mock_redis: MagicMock
    ) -> None:
        # Arrange
        user_id = uuid.uuid4()
        data = {"id": str(user_id), "name": "Alice", "email": "a@a.com", "age": 30}

        # Act
        await cache.set_user(user_id, data)

        # Assert — key must embed the user UUID
        mock_redis.setex.assert_awaited_once()
        key_used = mock_redis.setex.call_args.args[0]
        assert str(user_id) in key_used

    async def test_does_not_raise_on_redis_error(
        self, cache: UserCache, mock_redis: MagicMock
    ) -> None:
        # Arrange
        mock_redis.setex.side_effect = Exception("Redis is down")

        # Act / Assert — must be silent
        await cache.set_user(uuid.uuid4(), {"id": "x"})


class TestInvalidateUser:
    async def test_deletes_user_key_and_matching_list_keys(
        self, cache: UserCache, mock_redis: MagicMock
    ) -> None:
        # Arrange
        user_id = uuid.uuid4()
        list_key = "users:list:page=1:size=20"
        mock_redis.scan_iter.return_value = _async_iter([list_key])

        # Act
        await cache.invalidate_user(user_id)

        # Assert
        mock_redis.delete.assert_awaited_once()
        deleted_keys = mock_redis.delete.call_args.args
        assert any(str(user_id) in k for k in deleted_keys)
        assert list_key in deleted_keys

    async def test_does_not_raise_on_redis_error(
        self, cache: UserCache, mock_redis: MagicMock
    ) -> None:
        # Arrange
        mock_redis.scan_iter.side_effect = Exception("Redis is down")

        # Act / Assert — must be silent
        await cache.invalidate_user(uuid.uuid4())


class TestInvalidateUserLists:
    async def test_deletes_all_list_keys_without_touching_user_keys(
        self, cache: UserCache, mock_redis: MagicMock
    ) -> None:
        # Arrange
        list_keys = ["users:list:page=1:size=20", "users:list:page=2:size=20"]
        mock_redis.scan_iter.return_value = _async_iter(list_keys)

        # Act
        await cache.invalidate_user_lists()

        # Assert
        mock_redis.delete.assert_awaited_once()
        deleted_keys = mock_redis.delete.call_args.args
        assert set(deleted_keys) == set(list_keys)

    async def test_does_nothing_when_no_list_keys_exist(
        self, cache: UserCache, mock_redis: MagicMock
    ) -> None:
        # Arrange — scan_iter already returns empty by default

        # Act
        await cache.invalidate_user_lists()

        # Assert
        mock_redis.delete.assert_not_awaited()

    async def test_does_not_raise_on_redis_error(
        self, cache: UserCache, mock_redis: MagicMock
    ) -> None:
        # Arrange
        mock_redis.scan_iter.side_effect = Exception("Redis is down")

        # Act / Assert — must be silent
        await cache.invalidate_user_lists()


class TestGetUserList:
    async def test_returns_none_on_cache_miss(self, cache: UserCache) -> None:
        # mock_redis.get already returns None by default (fixture)
        result = await cache.get_user_list(page=1, page_size=20)

        assert result is None

    async def test_returns_parsed_dict_on_cache_hit(
        self, cache: UserCache, mock_redis: MagicMock
    ) -> None:
        # Arrange
        data = {"total": 0, "page": 1, "page_size": 20, "items": []}
        mock_redis.get.return_value = json.dumps(data)

        # Act
        result = await cache.get_user_list(page=1, page_size=20)

        # Assert
        assert result == data


class TestSetUserList:
    async def test_stores_data_with_list_ttl_shorter_than_user_ttl(
        self, cache: UserCache, mock_redis: MagicMock
    ) -> None:
        # Arrange
        data = {"total": 1, "page": 1, "page_size": 20, "items": []}

        # Act
        await cache.set_user_list(page=1, page_size=20, data=data)

        # Assert — list TTL must be strictly shorter than individual user TTL
        mock_redis.setex.assert_awaited_once()
        ttl_used = mock_redis.setex.call_args.args[1]
        assert ttl_used == cache._list_ttl
        assert cache._list_ttl < cache._ttl
