"""Tests for get_db_session — rollback and logging behaviour.

Two scenarios:
  1. DatabaseError  → rollback + ERROR log emitido
  2. Exception comum (ex: UserNotFoundError) → rollback silencioso, sem log de ERROR
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.exceptions import DatabaseError, UserNotFoundError
from app.database.session import get_db_session


# ---------------------------------------------------------------------------
# Fixture: sessão falsa que controla rollback e commit
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> MagicMock:
    """AsyncSession mock com rollback e commit rastreáveis."""
    session = MagicMock()
    session.rollback = AsyncMock()
    session.commit = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# Helpers para consumir o generator e forçar uma exceção dentro do yield
# ---------------------------------------------------------------------------


async def _drive_session(exc: Exception) -> None:
    """Abre a sessão via get_db_session, simula um erro dentro do bloco
    e deixa a exceção se propagar (para que o except do generator execute)."""
    gen = get_db_session()
    await gen.__anext__()          # avança até o yield — obtém a sessão
    try:
        await gen.athrow(exc)      # injeta a exceção no ponto do yield
    except type(exc):
        pass                       # exceção re-raised pelo generator — esperado


# ---------------------------------------------------------------------------
# Cenário 1: DatabaseError → rollback + logger.exception chamado
# ---------------------------------------------------------------------------


class TestDatabaseErrorScenario:
    async def test_rollback_is_called(self, mock_session: MagicMock) -> None:
        """get_db_session deve fazer rollback quando DatabaseError é lançada."""
        with patch(
            "app.database.session.AsyncSessionFactory",
            return_value=_ctx(mock_session),
        ):
            await _drive_session(DatabaseError("banco explodiu"))

        mock_session.rollback.assert_awaited_once()

    async def test_error_is_logged(self, mock_session: MagicMock) -> None:
        """get_db_session deve emitir logger.exception para DatabaseError."""
        with patch(
            "app.database.session.AsyncSessionFactory",
            return_value=_ctx(mock_session),
        ), patch("app.database.session.logger") as mock_logger:
            await _drive_session(DatabaseError("banco explodiu"))

        mock_logger.exception.assert_called_once()

    async def test_exception_is_re_raised(self, mock_session: MagicMock) -> None:
        """get_db_session deve re-raise DatabaseError após rollback."""
        with patch(
            "app.database.session.AsyncSessionFactory",
            return_value=_ctx(mock_session),
        ):
            with pytest.raises(DatabaseError):
                gen = get_db_session()
                await gen.__anext__()
                await gen.athrow(DatabaseError("banco explodiu"))


# ---------------------------------------------------------------------------
# Cenário 2: Exception comum (UserNotFoundError) → rollback silencioso
# ---------------------------------------------------------------------------


class TestGenericExceptionScenario:
    async def test_rollback_is_called(self, mock_session: MagicMock) -> None:
        """get_db_session deve fazer rollback mesmo para exceções de domínio."""
        with patch(
            "app.database.session.AsyncSessionFactory",
            return_value=_ctx(mock_session),
        ):
            await _drive_session(UserNotFoundError("não existe"))

        mock_session.rollback.assert_awaited_once()

    async def test_error_is_NOT_logged(self, mock_session: MagicMock) -> None:
        """get_db_session NÃO deve emitir logger.exception para erros de domínio.

        UserNotFoundError (404) e DuplicateEmailError (409) são fluxos normais —
        não devem aparecer como ERROR nos logs de infraestrutura.
        """
        with patch(
            "app.database.session.AsyncSessionFactory",
            return_value=_ctx(mock_session),
        ), patch("app.database.session.logger") as mock_logger:
            await _drive_session(UserNotFoundError("não existe"))

        mock_logger.exception.assert_not_called()

    async def test_exception_is_re_raised(self, mock_session: MagicMock) -> None:
        """get_db_session deve re-raise a exceção de domínio para o handler HTTP."""
        with patch(
            "app.database.session.AsyncSessionFactory",
            return_value=_ctx(mock_session),
        ):
            with pytest.raises(UserNotFoundError):
                gen = get_db_session()
                await gen.__anext__()
                await gen.athrow(UserNotFoundError("não existe"))


# ---------------------------------------------------------------------------
# Helper: context manager falso que entrega a sessão mock
# ---------------------------------------------------------------------------


class _ctx:
    """Simula o async context manager retornado por AsyncSessionFactory()."""

    def __init__(self, session: MagicMock) -> None:
        self._session = session

    async def __aenter__(self) -> MagicMock:
        return self._session

    async def __aexit__(self, *args: object) -> bool:
        return False  # não suprime exceções
