"""User preferences management.

Per docs/031 "USER PREFERENCES". Per "USER ACTIVITY": "Preference Changes"
is a tracked activity type -- fixed alongside the same gap in
:mod:`~app.services.profile` (found via live HTTP testing: ``GET
/users/activity`` stayed empty after updates) by threading
:class:`~app.services.activity.UserActivityService` through.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.constants import DEFAULT_ORGANIZATION_ID
from app.models.enums import ActivityType
from app.models.preferences import UserPreferences
from app.repositories.preferences import UserPreferencesRepository
from app.services.activity import UserActivityService


class UserPreferencesService:
    """Creates and updates platform preferences for a user."""

    def __init__(
        self, preferences: UserPreferencesRepository, activity: UserActivityService
    ) -> None:
        self._preferences = preferences
        self._activity = activity

    async def get_or_create(self, user_id: UUID) -> UserPreferences:
        """Return *user_id*'s preferences, creating defaults if they don't exist yet."""
        existing = await self._preferences.get_for_user(user_id)
        if existing is not None:
            return existing
        return await self._preferences.create(
            UserPreferences(user_id=user_id, organization_id=DEFAULT_ORGANIZATION_ID)
        )

    async def update(
        self,
        user_id: UUID,
        *,
        language: str,
        theme: str,
        timezone: str,
        date_format: str,
        time_format: str,
        dashboard_preferences: dict[str, Any],
        notification_preferences: dict[str, Any],
        accessibility: dict[str, Any],
        default_organization_id: UUID | None,
        default_project_id: UUID | None,
    ) -> UserPreferences:
        """Update *user_id*'s preferences, creating them first if needed ("Preference Changes")."""
        preferences = await self.get_or_create(user_id)
        preferences.language = language
        preferences.theme = theme
        preferences.timezone = timezone
        preferences.date_format = date_format
        preferences.time_format = time_format
        preferences.dashboard_preferences = dashboard_preferences
        preferences.notification_preferences = notification_preferences
        preferences.accessibility = accessibility
        preferences.default_organization_id = default_organization_id
        preferences.default_project_id = default_project_id
        await self._activity.record(user_id, activity_type=ActivityType.PREFERENCES_UPDATED)
        return preferences


__all__ = ["UserPreferencesService"]
