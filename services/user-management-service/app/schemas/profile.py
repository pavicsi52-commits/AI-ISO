"""Request/response schemas for the user profile."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ProfileUpdateRequest(BaseModel):
    """Body of a profile update."""

    biography: str | None = Field(default=None, max_length=4096)
    job_title: str | None = Field(default=None, max_length=255)
    department: str | None = Field(default=None, max_length=255)
    employee_id: str | None = Field(default=None, max_length=64)
    manager_id: UUID | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class ProfileResponse(BaseModel):
    """The full profile view."""

    user_id: UUID
    biography: str | None
    job_title: str | None
    department: str | None
    employee_id: str | None
    manager_id: UUID | None
    profile_photo: str | None
    custom_fields: dict[str, Any]


__all__ = ["ProfileResponse", "ProfileUpdateRequest"]
