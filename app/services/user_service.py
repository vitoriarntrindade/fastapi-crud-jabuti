"""Business logic for user management."""

import logging
import uuid

from app.cache.user_cache import UserCache
from app.repositories.user_repository import UserRepository
from app.schemas.user import (
    PaginatedUsersResponse,
    UserCreate,
    UserResponse,
    UserUpdate,
)

logger = logging.getLogger(__name__)


class UserService:
    """Orchestrates user operations across the repository and cache layers."""

    def __init__(self, repository: UserRepository, cache: UserCache) -> None:
        self._repo = repository
        self._cache = cache

    async def list_users(
        self, page: int, page_size: int
    ) -> PaginatedUsersResponse:
        """Return a paginated list of users, served from cache when available.

        Args:
            page: 1-based page number.
            page_size: Maximum number of items per page.

        Returns:
            A PaginatedUsersResponse with total count and current page items.
        """
        cached = await self._cache.get_user_list(page, page_size)
        if cached is not None:
            return PaginatedUsersResponse(**cached)

        users, total = await self._repo.list_paginated(page, page_size)
        response = PaginatedUsersResponse(
            total=total,
            page=page,
            page_size=page_size,
            items=[UserResponse.model_validate(u) for u in users],
        )
        await self._cache.set_user_list(
            page, page_size, response.model_dump(mode="json")
        )
        return response

    async def get_user(self, user_id: uuid.UUID) -> UserResponse:
        """Return a single user by ID, served from cache when available.

        Args:
            user_id: The UUID of the user to retrieve.

        Returns:
            A UserResponse with user details.

        Raises:
            UserNotFoundError: If the user does not exist.
        """
        cached = await self._cache.get_user(user_id)
        if cached is not None:
            return UserResponse(**cached)

        user = await self._repo.get_by_id(user_id)
        response = UserResponse.model_validate(user)
        await self._cache.set_user(user_id, response.model_dump(mode="json"))
        return response

    async def create_user(self, payload: UserCreate) -> UserResponse:
        """Create a new user and invalidate the list cache.

        Args:
            payload: Validated user creation data.

        Returns:
            The created UserResponse.

        Raises:
            DuplicateEmailError: If the email is already in use.
        """
        user = await self._repo.create(payload)
        response = UserResponse.model_validate(user)
        await self._cache.invalidate_user_lists()
        logger.info("User service: created user id=%s", user.id)
        return response

    async def update_user(
        self, user_id: uuid.UUID, payload: UserUpdate
    ) -> UserResponse:
        """Update an existing user and invalidate related cache entries.

        Args:
            user_id: Target user UUID.
            payload: Fields to update.

        Returns:
            The updated UserResponse.

        Raises:
            UserNotFoundError: If the user does not exist.
            DuplicateEmailError: If the new email conflicts.
        """
        user = await self._repo.update(user_id, payload)
        response = UserResponse.model_validate(user)
        await self._cache.invalidate_user(user_id)
        logger.info("User service: updated user id=%s", user_id)
        return response

    async def delete_user(self, user_id: uuid.UUID) -> None:
        """Delete a user and invalidate related cache entries.

        Args:
            user_id: The UUID of the user to delete.

        Raises:
            UserNotFoundError: If the user does not exist.
        """
        await self._repo.delete(user_id)
        await self._cache.invalidate_user(user_id)
        logger.info("User service: deleted user id=%s", user_id)
