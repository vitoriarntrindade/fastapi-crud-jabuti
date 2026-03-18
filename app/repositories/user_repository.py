"""Data-access layer for the users table."""

import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DatabaseError, DuplicateEmailError, UserNotFoundError
from app.database.models import User
from app.schemas.user import UserCreate, UserReplace, UserUpdate

logger = logging.getLogger(__name__)


class UserRepository:
    """Encapsulates all database operations for the User entity."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: uuid.UUID) -> User:
        """Fetch a single user by primary key.

        Args:
            user_id: The UUID of the user to retrieve.

        Returns:
            The User ORM instance.

        Raises:
            UserNotFoundError: If no user with the given ID exists.
        """
        result = await self._session.get(User, user_id)
        if result is None:
            raise UserNotFoundError(f"User {user_id} not found")
        return result

    async def list_paginated(
        self, page: int, page_size: int
    ) -> tuple[list[User], int]:
        """Return a paginated list of users along with the total count.

        Args:
            page: 1-based page number.
            page_size: Maximum number of records per page.

        Returns:
            A tuple of (list of User instances, total record count).
        """
        offset = (page - 1) * page_size

        count_result = await self._session.execute(select(func.count(User.id)))
        total: int = count_result.scalar_one()

        users_result = await self._session.execute(
            select(User).order_by(User.name).offset(offset).limit(page_size)
        )
        users = list(users_result.scalars().all())
        return users, total

    async def create(self, payload: UserCreate) -> User:
        """Persist a new user record.

        Args:
            payload: Validated creation data.

        Returns:
            The newly created User ORM instance.

        Raises:
            DuplicateEmailError: If the email already exists.
            DatabaseError: On any other unexpected database error.
        """
        user = User(
            id=uuid.uuid4(),
            name=payload.name,
            email=payload.email,
            age=payload.age,
        )
        self._session.add(user)
        try:
            await self._session.flush()
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            orig_msg = str(exc.orig).lower()
            if "uq_users_email" in orig_msg or "users.email" in orig_msg:
                raise DuplicateEmailError(
                    f"Email {payload.email!r} is already registered"
                ) from exc
            raise DatabaseError(
                "Unexpected database error during user creation"
            ) from exc
        logger.info("User created — id=%s email=%s", user.id, user.email)
        return user

    async def replace(self, user_id: uuid.UUID, payload: UserReplace) -> User:
        """Fully replace an existing user (PUT semantics).

        All fields are overwritten with the values provided in *payload*.
        No field is left unchanged — the resource is completely replaced.

        Args:
            user_id: Target user UUID.
            payload: Complete replacement data (all fields required).

        Returns:
            The updated User ORM instance.

        Raises:
            UserNotFoundError: If the user does not exist.
            DuplicateEmailError: If the new email conflicts with another user.
            DatabaseError: On any other unexpected database error.
        """
        user = await self.get_by_id(user_id)
        user.name = payload.name
        user.email = payload.email
        user.age = payload.age
        try:
            await self._session.flush()
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            orig_msg = str(exc.orig).lower()
            if "uq_users_email" in orig_msg or "users.email" in orig_msg:
                raise DuplicateEmailError(
                    f"Email {payload.email!r} is already registered"
                ) from exc
            raise DatabaseError(
                "Unexpected database error during user replace"
            ) from exc
        logger.info("User replaced — id=%s", user_id)
        return user

    async def update(self, user_id: uuid.UUID, payload: UserUpdate) -> User:
        """Apply partial updates to an existing user (PATCH semantics).

        Only fields explicitly provided (non-None) are written to the record.

        Returns:
            The updated User ORM instance.

        Raises:
            UserNotFoundError: If the user does not exist.
            DuplicateEmailError: If the new email conflicts with another user.
            DatabaseError: On any other unexpected database error.
        """
        user = await self.get_by_id(user_id)
        update_data = payload.model_dump(exclude_none=True)
        for field, value in update_data.items():
            setattr(user, field, value)
        try:
            await self._session.flush()
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            orig_msg = str(exc.orig).lower()
            if "uq_users_email" in orig_msg or "users.email" in orig_msg:
                raise DuplicateEmailError(
                    f"Email {payload.email!r} is already registered"
                ) from exc
            raise DatabaseError("Unexpected database error during user update") from exc
        logger.info("User updated — id=%s", user_id)
        return user

    async def delete(self, user_id: uuid.UUID) -> None:
        """Remove a user by ID.

        Args:
            user_id: The UUID of the user to delete.

        Raises:
            UserNotFoundError: If the user does not exist.
        """
        user = await self.get_by_id(user_id)
        await self._session.delete(user)
        await self._session.flush()
        await self._session.commit()
        logger.info("User deleted — id=%s", user_id)
