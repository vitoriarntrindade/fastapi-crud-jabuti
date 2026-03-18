"""FastAPI dependency providers for database sessions, cache, and services."""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.client import get_redis_client
from app.cache.user_cache import UserCache
from app.database.session import get_db_session
from app.repositories.user_repository import UserRepository
from app.services.user_service import UserService


async def get_user_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserRepository:
    """Provide a UserRepository bound to the current request session."""
    return UserRepository(session)


async def get_user_cache() -> AsyncGenerator[UserCache, None]:
    """Provide a UserCache bound to the shared Redis client."""
    client = await get_redis_client()
    yield UserCache(client)


async def get_user_service(
    repository: Annotated[UserRepository, Depends(get_user_repository)],
    cache: Annotated[UserCache, Depends(get_user_cache)],
) -> UserService:
    """Provide a fully wired UserService for injection into route handlers."""
    return UserService(repository, cache)
