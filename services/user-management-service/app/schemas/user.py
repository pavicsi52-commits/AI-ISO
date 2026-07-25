"""Request/response schemas for the ``/users`` CRUD/search surface."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator
from shared_core.validators.fields.credentials import validate_username

from app.models.enums import UserStatus


def validated_username(value: str) -> str:
    """Validate *value* against the platform username policy, raising ``ValueError`` if invalid."""
    result = validate_username(value)
    if not result.valid:
        raise ValueError("; ".join(result.errors))
    return value


class UserCreateRequest(BaseModel):
    """Body of ``POST /users``."""

    username: str
    email: EmailStr
    display_name: str | None = Field(default=None, max_length=255)
    first_name: str | None = Field(default=None, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    phone_number: str | None = Field(default=None, max_length=32)
    timezone: str = Field(default="UTC", max_length=64)
    language: str = Field(default="en", max_length=16)
    locale: str = Field(default="en-US", max_length=16)

    @field_validator("username")
    @classmethod
    def _validate_username(cls, value: str) -> str:
        return validated_username(value)


class UserUpdateRequest(BaseModel):
    """Body of ``PUT /users/{id}`` (full replace of the mutable fields)."""

    display_name: str | None = Field(default=None, max_length=255)
    first_name: str | None = Field(default=None, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    phone_number: str | None = Field(default=None, max_length=32)
    timezone: str = Field(default="UTC", max_length=64)
    language: str = Field(default="en", max_length=16)
    locale: str = Field(default="en-US", max_length=16)


class UserPatchRequest(BaseModel):
    """Body of ``PATCH /users/{id}`` (every field optional)."""

    display_name: str | None = Field(default=None, max_length=255)
    first_name: str | None = Field(default=None, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    phone_number: str | None = Field(default=None, max_length=32)
    timezone: str | None = Field(default=None, max_length=64)
    language: str | None = Field(default=None, max_length=16)
    locale: str | None = Field(default=None, max_length=16)
    status: UserStatus | None = None


class UserSummary(BaseModel):
    """A list/search-result view of a user."""

    id: UUID
    username: str
    email: str
    display_name: str | None
    avatar: str | None
    status: UserStatus
    created_at: datetime


class UserDetail(BaseModel):
    """The full view of a user returned by ``GET /users/{id}``."""

    id: UUID
    username: str
    email: str
    display_name: str | None
    first_name: str | None
    middle_name: str | None
    last_name: str | None
    phone_number: str | None
    avatar: str | None
    timezone: str
    language: str
    locale: str
    status: UserStatus
    last_login: datetime | None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class UserSearchRequest(BaseModel):
    """Body of ``POST /users/search``."""

    query: str | None = None
    status: UserStatus | None = None
    department: str | None = None
    tags: list[str] = Field(default_factory=list)
    sort: str | None = Field(default=None, description="e.g. 'created_at:desc,username:asc'")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=200)


__all__ = [
    "UserCreateRequest",
    "UserDetail",
    "UserPatchRequest",
    "UserSearchRequest",
    "UserSummary",
    "UserUpdateRequest",
    "validated_username",
]
