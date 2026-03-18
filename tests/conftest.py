"""Shared pytest fixtures for the test suite."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.cache.user_cache import UserCache
from app.database.models import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserUpdate
from app.services.user_service import UserService


@pytest.fixture
def sample_user() -> User:
    """Return a detached User ORM instance for testing."""
    return User(
        id=uuid.uuid4(),
        name="Alice Smith",
        email="alice@example.com",
        age=30,
    )


@pytest.fixture
def user_create_payload() -> UserCreate:
    """Return a UserCreate payload matching sample_user's data."""
    return UserCreate(name="Alice Smith", email="alice@example.com", age=30)


@pytest.fixture
def user_update_payload() -> UserUpdate:
    """Return a partial UserUpdate payload for testing field updates."""
    return UserUpdate(name="Alice Updated", age=31)


@pytest.fixture
def mock_repository(sample_user: User) -> MagicMock:
    """Return a MagicMock of UserRepository with pre-configured async stubs."""
    repo = MagicMock(spec=UserRepository)
    repo.get_by_id = AsyncMock(return_value=sample_user)
    repo.list_paginated = AsyncMock(return_value=([sample_user], 1))
    repo.create = AsyncMock(return_value=sample_user)
    repo.update = AsyncMock(return_value=sample_user)
    repo.delete = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def mock_cache() -> MagicMock:
    """Return a MagicMock of UserCache with pre-configured async stubs."""
    cache = MagicMock(spec=UserCache)
    cache.get_user = AsyncMock(return_value=None)
    cache.set_user = AsyncMock(return_value=None)
    cache.get_user_list = AsyncMock(return_value=None)
    cache.set_user_list = AsyncMock(return_value=None)
    cache.invalidate_user = AsyncMock(return_value=None)
    cache.invalidate_user_lists = AsyncMock(return_value=None)
    return cache


@pytest.fixture
def user_service(mock_repository: MagicMock, mock_cache: MagicMock) -> UserService:
    """Return a UserService wired with mock repository and cache."""
    return UserService(repository=mock_repository, cache=mock_cache)
