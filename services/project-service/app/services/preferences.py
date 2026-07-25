"""Project preferences management -- no dedicated REST surface in
docs/034's own endpoint list, matching
``app/services/business_unit.py``-equivalent scope decisions across
this codebase (full service-layer support for programmatic
completeness, no REST exposure this prompt).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.project_preferences import ProjectPreferences
from app.repositories.project_preferences import ProjectPreferencesRepository


class ProjectPreferencesService:
    """Reads and updates a project's UI/dashboard preferences."""

    def __init__(self, preferences: ProjectPreferencesRepository) -> None:
        self._preferences = preferences

    async def get_or_create(self, project_id: UUID, *, organization_id: UUID) -> ProjectPreferences:
        """Return *project_id*'s preferences, creating defaults if missing."""
        existing = await self._preferences.get_for_project(project_id)
        if existing is not None:
            return existing
        return await self._preferences.create(
            ProjectPreferences(project_id=project_id, organization_id=organization_id)
        )

    async def update(
        self,
        project_id: UUID,
        *,
        organization_id: UUID,
        dashboard_layout: dict[str, Any],
        notification_preferences: dict[str, Any],
        ui_preferences: dict[str, Any],
    ) -> ProjectPreferences:
        """Update *project_id*'s preferences."""
        preferences = await self.get_or_create(project_id, organization_id=organization_id)
        preferences.dashboard_layout = dashboard_layout
        preferences.notification_preferences = notification_preferences
        preferences.ui_preferences = ui_preferences
        return preferences


__all__ = ["ProjectPreferencesService"]
