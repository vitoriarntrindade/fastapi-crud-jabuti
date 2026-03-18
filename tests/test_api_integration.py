"""Integration tests for the Users API.

These tests exercise the full request/response cycle — router → service →
repository → in-memory SQLite database — without requiring a running
PostgreSQL or Redis instance.

Strategy:
- SQLite (aiosqlite) replaces PostgreSQL: same SQLAlchemy ORM, zero infra.
- Redis is replaced by a no-op cache so every read goes straight to the DB,
  making assertions deterministic and side-effect-free.
- FastAPI dependency overrides wire the test engine and cache into the app.
"""

import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.dependencies import get_db_session, get_user_cache
from app.cache.user_cache import UserCache
from app.database.models import Base
from app.main import app

# ---------------------------------------------------------------------------
# In-memory SQLite engine (created fresh for every test session)
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

_test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
_TestSessionFactory = async_sessionmaker(
    bind=_test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _create_tables() -> AsyncGenerator[None, None]:
    """Create all ORM tables in the in-memory database once per session."""
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await _test_engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables() -> AsyncGenerator[None, None]:
    """Truncate all tables between tests so each test starts with a clean DB."""
    yield
    async with _test_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


@pytest.fixture
def no_op_cache() -> MagicMock:
    """Return a UserCache mock that always reports a cache miss.

    This keeps every test deterministic: all reads go to the database,
    and write-side invalidations are still recorded for assertion.
    """
    cache = MagicMock(spec=UserCache)
    cache.get_user = AsyncMock(return_value=None)
    cache.set_user = AsyncMock(return_value=None)
    cache.get_user_list = AsyncMock(return_value=None)
    cache.set_user_list = AsyncMock(return_value=None)
    cache.invalidate_user = AsyncMock(return_value=None)
    cache.invalidate_user_lists = AsyncMock(return_value=None)
    return cache


@pytest_asyncio.fixture
async def client(no_op_cache: MagicMock) -> AsyncGenerator[AsyncClient, None]:
    """Return an AsyncClient wired against the in-memory database and no-op cache."""

    async def override_db() -> AsyncGenerator[AsyncSession, None]:
        async with _TestSessionFactory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    async def override_cache() -> AsyncGenerator[Any, None]:
        yield no_op_cache

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_user_cache] = override_cache

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def _create_user(
    client: AsyncClient,
    *,
    name: str = "Alice Smith",
    email: str = "alice@example.com",
    age: int = 30,
) -> dict[str, Any]:
    response = await client.post(
        "/users", json={"name": name, "email": email, "age": age}
    )
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    async def test_health_returns_ok(self, client: AsyncClient) -> None:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


class TestCreateUser:
    async def test_creates_user_and_returns_201(self, client: AsyncClient) -> None:
        response = await client.post(
            "/users",
            json={"name": "Alice Smith", "email": "alice@example.com", "age": 30},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["email"] == "alice@example.com"
        assert body["name"] == "Alice Smith"
        assert body["age"] == 30
        assert "id" in body

    async def test_returns_409_on_duplicate_email(self, client: AsyncClient) -> None:
        await _create_user(client, email="dup@example.com")
        response = await client.post(
            "/users",
            json={"name": "Bob", "email": "dup@example.com", "age": 25},
        )
        assert response.status_code == 409

    async def test_returns_422_on_invalid_payload(self, client: AsyncClient) -> None:
        response = await client.post(
            "/users",
            json={"name": "", "email": "not-an-email", "age": -1},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Get
# ---------------------------------------------------------------------------


class TestGetUser:
    async def test_returns_user_by_id(self, client: AsyncClient) -> None:
        created = await _create_user(client)
        response = await client.get(f"/users/{created['id']}")
        assert response.status_code == 200
        assert response.json()["email"] == created["email"]

    async def test_returns_404_for_unknown_id(self, client: AsyncClient) -> None:
        response = await client.get(f"/users/{uuid.uuid4()}")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


class TestListUsers:
    async def test_returns_empty_list_initially(self, client: AsyncClient) -> None:
        response = await client.get("/users")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 0
        assert body["items"] == []

    async def test_returns_created_users_in_list(self, client: AsyncClient) -> None:
        await _create_user(client, email="u1@example.com")
        await _create_user(client, email="u2@example.com")
        response = await client.get("/users?page=1&page_size=20")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2
        assert len(body["items"]) == 2

    async def test_pagination_limits_items_per_page(
        self, client: AsyncClient
    ) -> None:
        for i in range(5):
            await _create_user(client, email=f"user{i}@example.com")
        response = await client.get("/users?page=1&page_size=3")
        body = response.json()
        assert body["total"] == 5
        assert len(body["items"]) == 3


# ---------------------------------------------------------------------------
# Replace (PUT)
# ---------------------------------------------------------------------------


class TestReplaceUser:
    async def test_replaces_all_user_fields(self, client: AsyncClient) -> None:
        created = await _create_user(client)
        response = await client.put(
            f"/users/{created['id']}",
            json={"name": "Alice Replaced", "email": "replaced@example.com", "age": 99},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "Alice Replaced"
        assert body["email"] == "replaced@example.com"
        assert body["age"] == 99

    async def test_returns_422_when_field_is_missing(self, client: AsyncClient) -> None:
        """PUT must reject partial payloads — all fields are required."""
        created = await _create_user(client)
        response = await client.put(
            f"/users/{created['id']}",
            json={"name": "No Email Or Age"},
        )
        assert response.status_code == 422

    async def test_returns_404_for_unknown_id(self, client: AsyncClient) -> None:
        response = await client.put(
            f"/users/{uuid.uuid4()}",
            json={"name": "Ghost", "email": "ghost@example.com", "age": 0},
        )
        assert response.status_code == 404

    async def test_returns_409_on_email_conflict(self, client: AsyncClient) -> None:
        u1 = await _create_user(client, email="u1@example.com")
        await _create_user(client, email="u2@example.com")
        response = await client.put(
            f"/users/{u1['id']}",
            json={"name": u1["name"], "email": "u2@example.com", "age": u1["age"]},
        )
        assert response.status_code == 409


# ---------------------------------------------------------------------------
# Partial update (PATCH)
# ---------------------------------------------------------------------------


class TestPatchUser:
    async def test_updates_only_provided_fields(self, client: AsyncClient) -> None:
        created = await _create_user(client)
        response = await client.patch(
            f"/users/{created['id']}",
            json={"name": "Alice Patched", "age": 31},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "Alice Patched"
        assert body["age"] == 31
        assert body["email"] == created["email"]  # unchanged field preserved

    async def test_returns_404_for_unknown_id(self, client: AsyncClient) -> None:
        response = await client.patch(
            f"/users/{uuid.uuid4()}", json={"name": "Ghost"}
        )
        assert response.status_code == 404

    async def test_returns_409_on_email_conflict(self, client: AsyncClient) -> None:
        u1 = await _create_user(client, email="u1@example.com")
        await _create_user(client, email="u2@example.com")
        response = await client.patch(
            f"/users/{u1['id']}", json={"email": "u2@example.com"}
        )
        assert response.status_code == 409


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


class TestDeleteUser:
    async def test_deletes_user_and_returns_204(self, client: AsyncClient) -> None:
        created = await _create_user(client)
        response = await client.delete(f"/users/{created['id']}")
        assert response.status_code == 204

    async def test_get_after_delete_returns_404(self, client: AsyncClient) -> None:
        created = await _create_user(client)
        await client.delete(f"/users/{created['id']}")
        response = await client.get(f"/users/{created['id']}")
        assert response.status_code == 404

    async def test_returns_404_for_unknown_id(self, client: AsyncClient) -> None:
        response = await client.delete(f"/users/{uuid.uuid4()}")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Full lifecycle: create → get → update → get updated → delete → 404
# ---------------------------------------------------------------------------


class TestFullCRUDLifecycle:
    async def test_create_get_update_get_delete(self, client: AsyncClient) -> None:
        # 1. Create
        created = await _create_user(
            client, name="Carol", email="carol@example.com", age=28
        )
        user_id = created["id"]
        assert created["name"] == "Carol"

        # 2. GET — data matches what was created
        get_response = await client.get(f"/users/{user_id}")
        assert get_response.status_code == 200
        assert get_response.json()["email"] == "carol@example.com"

        # 3. Replace (PUT — all fields required)
        update_response = await client.put(
            f"/users/{user_id}",
            json={"name": "Carol Updated", "email": "carol@example.com", "age": 29},
        )
        assert update_response.status_code == 200
        assert update_response.json()["name"] == "Carol Updated"

        # 4. GET after update — reflects new values
        get_after_update = await client.get(f"/users/{user_id}")
        assert get_after_update.status_code == 200
        assert get_after_update.json()["name"] == "Carol Updated"
        assert get_after_update.json()["age"] == 29
        assert get_after_update.json()["email"] == "carol@example.com"

        # 5. Delete
        del_response = await client.delete(f"/users/{user_id}")
        assert del_response.status_code == 204

        # 6. GET after delete → 404
        get_after_delete = await client.get(f"/users/{user_id}")
        assert get_after_delete.status_code == 404
