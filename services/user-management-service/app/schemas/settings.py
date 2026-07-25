"""Request/response schemas for ``GET/PUT /users/settings``."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class SettingsUpdateRequest(BaseModel):
    """Body of ``PUT /users/settings``."""

    display_settings: dict[str, Any] = Field(default_factory=dict)
    privacy: dict[str, Any] = Field(default_factory=dict)
    security_preferences: dict[str, Any] = Field(default_factory=dict)
    default_views: dict[str, Any] = Field(default_factory=dict)
    shortcuts: dict[str, Any] = Field(default_factory=dict)
    favorites: list[str] = Field(default_factory=list)
    feature_flags: dict[str, Any] = Field(default_factory=dict)


class SettingsResponse(BaseModel):
    """The full settings view."""

    user_id: UUID
    display_settings: dict[str, Any]
    privacy: dict[str, Any]
    security_preferences: dict[str, Any]
    default_views: dict[str, Any]
    shortcuts: dict[str, Any]
    favorites: list[str]
    feature_flags: dict[str, Any]


__all__ = ["SettingsResponse", "SettingsUpdateRequest"]
