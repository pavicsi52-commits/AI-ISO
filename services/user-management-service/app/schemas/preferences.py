"""Request/response schemas for ``GET/PUT /users/preferences``."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class PreferencesUpdateRequest(BaseModel):
    """Body of ``PUT /users/preferences``."""

    language: str = Field(default="en", max_length=16)
    theme: str = Field(default="system", max_length=32)
    timezone: str = Field(default="UTC", max_length=64)
    date_format: str = Field(default="YYYY-MM-DD", max_length=32)
    time_format: str = Field(default="24h", max_length=16)
    dashboard_preferences: dict[str, Any] = Field(default_factory=dict)
    notification_preferences: dict[str, Any] = Field(default_factory=dict)
    accessibility: dict[str, Any] = Field(default_factory=dict)
    default_organization_id: UUID | None = None
    default_project_id: UUID | None = None


class PreferencesResponse(BaseModel):
    """The full preferences view."""

    user_id: UUID
    language: str
    theme: str
    timezone: str
    date_format: str
    time_format: str
    dashboard_preferences: dict[str, Any]
    notification_preferences: dict[str, Any]
    accessibility: dict[str, Any]
    default_organization_id: UUID | None
    default_project_id: UUID | None


__all__ = ["PreferencesResponse", "PreferencesUpdateRequest"]
