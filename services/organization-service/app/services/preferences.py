"""Organization preferences management. Per docs/033's "Organization Preferences" objective."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.organization_preferences import OrganizationPreferences
from app.repositories.organization_preferences import OrganizationPreferencesRepository


class OrganizationPreferencesService:
    """Reads and updates an organization's UI/dashboard preferences."""

    def __init__(self, preferences: OrganizationPreferencesRepository) -> None:
        self._preferences = preferences

    async def get_or_create(self, organization_id: UUID) -> OrganizationPreferences:
        """Return *organization_id*'s preferences, creating defaults if missing."""
        existing = await self._preferences.get_for_org(organization_id)
        if existing is not None:
            return existing
        return await self._preferences.create(
            OrganizationPreferences(organization_id=organization_id)
        )

    async def update(
        self,
        organization_id: UUID,
        *,
        dashboard_layout: dict[str, Any],
        notification_preferences: dict[str, Any],
        ui_preferences: dict[str, Any],
    ) -> OrganizationPreferences:
        """Update *organization_id*'s preferences."""
        preferences = await self.get_or_create(organization_id)
        preferences.dashboard_layout = dashboard_layout
        preferences.notification_preferences = notification_preferences
        preferences.ui_preferences = ui_preferences
        return preferences


__all__ = ["OrganizationPreferencesService"]
