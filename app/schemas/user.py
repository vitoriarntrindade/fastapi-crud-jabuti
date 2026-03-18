"""Pydantic schemas for User request/response contracts."""

import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    """Payload for creating a new user."""

    name: str = Field(..., min_length=1, max_length=255, examples=["Alice Smith"])
    email: EmailStr = Field(..., examples=["alice@example.com"])
    age: int = Field(..., ge=0, le=150, examples=[30])


class UserReplace(BaseModel):
    """Payload for fully replacing an existing user (PUT semantics — all fields required)."""

    name: str = Field(..., min_length=1, max_length=255, examples=["Alice Smith"])
    email: EmailStr = Field(..., examples=["alice@example.com"])
    age: int = Field(..., ge=0, le=150, examples=[30])


class UserUpdate(BaseModel):
    """Payload for partially updating an existing user (PATCH semantics — all fields optional)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: EmailStr | None = Field(default=None)
    age: int | None = Field(default=None, ge=0, le=150)


class UserResponse(BaseModel):
    """Public representation of a user returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str
    age: int


class PaginatedUsersResponse(BaseModel):
    """Paginated list of users."""

    total: int
    page: int
    page_size: int
    items: list[UserResponse]
