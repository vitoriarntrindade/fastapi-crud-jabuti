"""Tests for UserService business logic."""

import uuid
from unittest.mock import MagicMock

import pytest

from app.core.exceptions import DuplicateEmailError, UserNotFoundError
from app.database.models import User
from app.schemas.user import UserCreate, UserUpdate
from app.services.user_service import UserService


class TestListUsers:
    async def test_returns_cached_response_without_hitting_db(
        self,
        user_service: UserService,
        mock_cache: MagicMock,
        mock_repository: MagicMock,
    ) -> None:
        # Arrange
        mock_cache.get_user_list.return_value = {
            "total": 1,
            "page": 1,
            "page_size": 20,
            "items": [
                {
                    "id": str(uuid.uuid4()),
                    "name": "Alice",
                    "email": "alice@example.com",
                    "age": 30,
                }
            ],
        }

        # Act
        result = await user_service.list_users(page=1, page_size=20)

        # Assert
        assert result.total == 1
        mock_repository.list_paginated.assert_not_awaited()
        mock_cache.set_user_list.assert_not_awaited()

    async def test_fetches_from_db_and_populates_cache_on_miss(
        self,
        user_service: UserService,
        mock_repository: MagicMock,
        mock_cache: MagicMock,
    ) -> None:
        # Arrange — cache miss is the default in the fixture

        # Act
        result = await user_service.list_users(page=1, page_size=20)

        # Assert
        mock_repository.list_paginated.assert_awaited_once_with(1, 20)
        mock_cache.set_user_list.assert_awaited_once()
        assert result.total == 1

    async def test_passes_pagination_params_to_repository(
        self, user_service: UserService, mock_repository: MagicMock
    ) -> None:
        # Act
        result = await user_service.list_users(page=3, page_size=5)

        # Assert
        mock_repository.list_paginated.assert_awaited_once_with(3, 5)
        assert result.page == 3
        assert result.page_size == 5


class TestGetUser:
    async def test_returns_cached_user_without_hitting_db(
        self,
        user_service: UserService,
        mock_cache: MagicMock,
        mock_repository: MagicMock,
        sample_user: User,
    ) -> None:
        # Arrange
        mock_cache.get_user.return_value = {
            "id": str(sample_user.id),
            "name": sample_user.name,
            "email": sample_user.email,
            "age": sample_user.age,
        }

        # Act
        result = await user_service.get_user(sample_user.id)

        # Assert
        assert result.email == sample_user.email
        mock_repository.get_by_id.assert_not_awaited()
        mock_cache.set_user.assert_not_awaited()

    async def test_fetches_from_db_and_populates_cache_on_miss(
        self,
        user_service: UserService,
        mock_repository: MagicMock,
        mock_cache: MagicMock,
        sample_user: User,
    ) -> None:
        # Arrange — cache miss is the default in the fixture

        # Act
        result = await user_service.get_user(sample_user.id)

        # Assert
        mock_repository.get_by_id.assert_awaited_once_with(sample_user.id)
        mock_cache.set_user.assert_awaited_once()
        assert result.id == sample_user.id

    async def test_propagates_user_not_found_error(
        self,
        user_service: UserService,
        mock_repository: MagicMock,
    ) -> None:
        # Arrange
        missing_id = uuid.uuid4()
        mock_repository.get_by_id.side_effect = UserNotFoundError(
            f"User {missing_id} not found"
        )

        # Act / Assert
        with pytest.raises(UserNotFoundError):
            await user_service.get_user(missing_id)


class TestCreateUser:
    async def test_creates_user_invalidates_list_cache_and_returns_response(
        self,
        user_service: UserService,
        mock_repository: MagicMock,
        mock_cache: MagicMock,
        user_create_payload: UserCreate,
        sample_user: User,
    ) -> None:
        # Act
        result = await user_service.create_user(user_create_payload)

        # Assert
        mock_repository.create.assert_awaited_once_with(user_create_payload)
        # On create, only list cache is invalidated — no per-user key exists yet
        mock_cache.invalidate_user_lists.assert_awaited_once()
        mock_cache.invalidate_user.assert_not_awaited()
        assert result.email == sample_user.email

    async def test_propagates_duplicate_email_error(
        self,
        user_service: UserService,
        mock_repository: MagicMock,
        user_create_payload: UserCreate,
    ) -> None:
        # Arrange
        mock_repository.create.side_effect = DuplicateEmailError(
            "Email already registered"
        )

        # Act / Assert
        with pytest.raises(DuplicateEmailError):
            await user_service.create_user(user_create_payload)


class TestUpdateUser:
    async def test_updates_user_invalidates_cache_and_returns_response(
        self,
        user_service: UserService,
        mock_repository: MagicMock,
        mock_cache: MagicMock,
        sample_user: User,
        user_update_payload: UserUpdate,
    ) -> None:
        # Act
        result = await user_service.update_user(sample_user.id, user_update_payload)

        # Assert
        mock_repository.update.assert_awaited_once_with(
            sample_user.id, user_update_payload
        )
        mock_cache.invalidate_user.assert_awaited_once_with(sample_user.id)
        assert result.id == sample_user.id

    async def test_propagates_user_not_found_error(
        self,
        user_service: UserService,
        mock_repository: MagicMock,
        user_update_payload: UserUpdate,
    ) -> None:
        # Arrange
        missing_id = uuid.uuid4()
        mock_repository.update.side_effect = UserNotFoundError(
            f"User {missing_id} not found"
        )

        # Act / Assert
        with pytest.raises(UserNotFoundError):
            await user_service.update_user(missing_id, user_update_payload)


class TestDeleteUser:
    async def test_deletes_user_and_invalidates_cache(
        self,
        user_service: UserService,
        mock_repository: MagicMock,
        mock_cache: MagicMock,
        sample_user: User,
    ) -> None:
        # Act
        await user_service.delete_user(sample_user.id)

        # Assert
        mock_repository.delete.assert_awaited_once_with(sample_user.id)
        mock_cache.invalidate_user.assert_awaited_once_with(sample_user.id)

    async def test_propagates_user_not_found_error(
        self,
        user_service: UserService,
        mock_repository: MagicMock,
    ) -> None:
        # Arrange
        missing_id = uuid.uuid4()
        mock_repository.delete.side_effect = UserNotFoundError(
            f"User {missing_id} not found"
        )

        # Act / Assert
        with pytest.raises(UserNotFoundError):
            await user_service.delete_user(missing_id)
