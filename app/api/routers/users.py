"""Users CRUD router."""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_user_service
from app.core.exceptions import DuplicateEmailError, UserNotFoundError
from app.schemas.user import (
    PaginatedUsersResponse,
    UserCreate,
    UserReplace,
    UserResponse,
    UserUpdate,
)
from app.services.user_service import UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=PaginatedUsersResponse)
async def list_users(
    service: Annotated[UserService, Depends(get_user_service)],
    page: int = Query(default=1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
) -> PaginatedUsersResponse:
    """List all users with pagination.

    Results are served from Redis cache when available.
    """
    logger.debug("GET /users page=%d page_size=%d", page, page_size)
    return await service.list_users(page=page, page_size=page_size)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: uuid.UUID,
    service: Annotated[UserService, Depends(get_user_service)],
) -> UserResponse:
    """Retrieve a single user by ID.

    Result is served from Redis cache when available.
    """
    logger.debug("GET /users/%s", user_id)
    try:
        return await service.get_user(user_id)
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    service: Annotated[UserService, Depends(get_user_service)],
) -> UserResponse:
    """Create a new user.

    Invalidates the user list cache.
    """
    logger.debug("POST /users email=%s", payload.email)
    try:
        return await service.create_user(payload)
    except DuplicateEmailError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc


@router.put("/{user_id}", response_model=UserResponse)
async def replace_user(
    user_id: uuid.UUID,
    payload: UserReplace,
    service: Annotated[UserService, Depends(get_user_service)],
) -> UserResponse:
    """Fully replace an existing user (PUT semantics).

    All fields are required. The resource is completely overwritten with the
    provided data — omitting a field is not the same as leaving it unchanged.
    Invalidates cache entries for this user and all list pages.
    """
    logger.debug("PUT /users/%s", user_id)
    try:
        return await service.replace_user(user_id, payload)
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except DuplicateEmailError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    service: Annotated[UserService, Depends(get_user_service)],
) -> UserResponse:
    """Partially update an existing user (PATCH semantics).

    Only the fields provided are updated; omitted fields remain unchanged.
    Invalidates cache entries for this user and all list pages.
    """
    logger.debug("PATCH /users/%s", user_id)
    try:
        return await service.update_user(user_id, payload)
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except DuplicateEmailError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    service: Annotated[UserService, Depends(get_user_service)],
) -> None:
    """Delete a user by ID.

    Invalidates cache entries for this user and all list pages.
    """
    logger.debug("DELETE /users/%s", user_id)
    try:
        await service.delete_user(user_id)
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
