"""User settings management. Per docs/031 "USER SETTINGS"."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.constants import DEFAULT_ORGANIZATION_ID
from app.models.settings import UserSettings
from app.repositories.settings import UserSettingsRepository


class UserSettingsService:
    """Creates and updates application-behavior settings for a user."""

    def __init__(self, settings: UserSettingsRepository) -> None:
        self._settings = settings

    async def get_or_create(self, user_id: UUID) -> UserSettings:
        """Return *user_id*'s settings, creating defaults if they don't exist yet."""
        existing = await self._settings.get_for_user(user_id)
        if existing is not None:
            return existing
        return await self._settings.create(
            UserSettings(user_id=user_id, organization_id=DEFAULT_ORGANIZATION_ID)
        )

    async def update(
        self,
        user_id: UUID,
        *,
        display_settings: dict[str, Any],
        privacy: dict[str, Any],
        security_preferences: dict[str, Any],
        default_views: dict[str, Any],
        shortcuts: dict[str, Any],
        favorites: list[str],
        feature_flags: dict[str, Any],
    ) -> UserSettings:
        """Update *user_id*'s settings, creating them first if necessary."""
        settings = await self.get_or_create(user_id)
        settings.display_settings = display_settings
        settings.privacy = privacy
        settings.security_preferences = security_preferences
        settings.default_views = default_views
        settings.shortcuts = shortcuts
        settings.favorites = favorites
        settings.feature_flags = feature_flags
        return settings


__all__ = ["UserSettingsService"]
