"""Tests for UserRepository data-access logic."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import DatabaseError, DuplicateEmailError, UserNotFoundError
from app.database.models import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserReplace, UserUpdate

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_CAROL_PAYLOAD = UserCreate(name="Carol", email="carol@example.com", age=28)


@pytest.fixture
def mock_session() -> MagicMock:
    """Return a fully stubbed AsyncSession-like mock."""
    session = MagicMock()
    session.get = AsyncMock()
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.delete = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.fixture
def repo(mock_session: MagicMock) -> UserRepository:
    """Return a UserRepository wired with the mock session."""
    return UserRepository(session=mock_session)


@pytest.fixture
def existing_user() -> User:
    """Return a detached User instance representing an existing DB record."""
    return User(id=uuid.uuid4(), name="Bob", email="bob@example.com", age=25)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGetById:
    async def test_returns_user_when_found(
        self, repo: UserRepository, mock_session: MagicMock, existing_user: User
    ) -> None:
        # Arrange
        mock_session.get.return_value = existing_user

        # Act
        result = await repo.get_by_id(existing_user.id)

        # Assert
        assert result.email == existing_user.email

    async def test_raises_user_not_found_when_missing(
        self, repo: UserRepository, mock_session: MagicMock
    ) -> None:
        # Arrange
        mock_session.get.return_value = None

        # Act / Assert
        with pytest.raises(UserNotFoundError):
            await repo.get_by_id(uuid.uuid4())


class TestCreate:
    async def test_persists_user_and_returns_it(
        self, repo: UserRepository, mock_session: MagicMock
    ) -> None:
        # Act
        result = await repo.create(_CAROL_PAYLOAD)

        # Assert
        mock_session.add.assert_called_once()
        mock_session.flush.assert_awaited_once()
        mock_session.commit.assert_awaited_once()
        assert result.email == _CAROL_PAYLOAD.email

    async def test_commit_follows_flush(
        self, repo: UserRepository, mock_session: MagicMock
    ) -> None:
        """Ensure commit happens after flush so cache invalidation
        sees committed data."""
        # Arrange
        call_order: list[str] = []
        mock_session.flush = AsyncMock(side_effect=lambda: call_order.append("flush"))
        mock_session.commit = AsyncMock(side_effect=lambda: call_order.append("commit"))

        # Act
        await repo.create(_CAROL_PAYLOAD)

        # Assert
        assert call_order == ["flush", "commit"]

    async def test_raises_duplicate_email_on_unique_constraint_violation(
        self, repo: UserRepository, mock_session: MagicMock
    ) -> None:
        # Arrange
        mock_session.flush.side_effect = IntegrityError(
            statement=None, params=None, orig=Exception("uq_users_email")
        )

        # Act / Assert
        with pytest.raises(DuplicateEmailError):
            await repo.create(_CAROL_PAYLOAD)

    async def test_raises_database_error_on_unknown_integrity_error(
        self, repo: UserRepository, mock_session: MagicMock
    ) -> None:
        # Arrange
        mock_session.flush.side_effect = IntegrityError(
            statement=None, params=None, orig=Exception("some other constraint")
        )

        # Act / Assert
        with pytest.raises(DatabaseError):
            await repo.create(_CAROL_PAYLOAD)


class TestReplace:
    async def test_overwrites_all_fields_and_returns_user(
        self,
        repo: UserRepository,
        mock_session: MagicMock,
        existing_user: User,
    ) -> None:
        # Arrange
        mock_session.get.return_value = existing_user
        payload = UserReplace(
            name="Bob Replaced", email="replaced@example.com", age=99
        )

        # Act
        result = await repo.replace(existing_user.id, payload)

        # Assert
        assert result.name == "Bob Replaced"
        assert result.email == "replaced@example.com"
        assert result.age == 99

    async def test_raises_duplicate_email_on_conflict(
        self,
        repo: UserRepository,
        mock_session: MagicMock,
        existing_user: User,
    ) -> None:
        # Arrange
        mock_session.get.return_value = existing_user
        mock_session.flush.side_effect = IntegrityError(
            statement=None, params=None, orig=Exception("uq_users_email")
        )
        payload = UserReplace(
            name="Bob", email="conflict@example.com", age=25
        )

        # Act / Assert
        with pytest.raises(DuplicateEmailError):
            await repo.replace(existing_user.id, payload)

    async def test_raises_user_not_found_when_missing(
        self, repo: UserRepository, mock_session: MagicMock
    ) -> None:
        # Arrange
        mock_session.get.return_value = None
        payload = UserReplace(name="Ghost", email="ghost@example.com", age=0)

        # Act / Assert
        with pytest.raises(UserNotFoundError):
            await repo.replace(uuid.uuid4(), payload)


class TestUpdate:
    async def test_applies_provided_fields_and_returns_user(
        self,
        repo: UserRepository,
        mock_session: MagicMock,
        existing_user: User,
    ) -> None:
        # Arrange
        mock_session.get.return_value = existing_user
        payload = UserUpdate(name="Bob Updated")

        # Act
        result = await repo.update(existing_user.id, payload)

        # Assert
        assert result.name == "Bob Updated"

    async def test_leaves_none_fields_unchanged(
        self,
        repo: UserRepository,
        mock_session: MagicMock,
        existing_user: User,
    ) -> None:
        # Arrange
        mock_session.get.return_value = existing_user
        original_email = existing_user.email
        payload = UserUpdate(age=99)

        # Act
        result = await repo.update(existing_user.id, payload)

        # Assert
        assert result.email == original_email
        assert result.age == 99


class TestDelete:
    async def test_removes_user_from_session(
        self,
        repo: UserRepository,
        mock_session: MagicMock,
        existing_user: User,
    ) -> None:
        # Arrange
        mock_session.get.return_value = existing_user

        # Act
        await repo.delete(existing_user.id)

        # Assert
        mock_session.delete.assert_awaited_once_with(existing_user)

    async def test_raises_user_not_found_when_missing(
        self, repo: UserRepository, mock_session: MagicMock
    ) -> None:
        # Arrange
        mock_session.get.return_value = None

        # Act / Assert
        with pytest.raises(UserNotFoundError):
            await repo.delete(uuid.uuid4())
