"""Project settings management. Per docs/034 "PROJECT SETTINGS"."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.enums import ProjectActivityType
from app.models.project_settings import ProjectSettings
from app.repositories.project_settings import ProjectSettingsRepository
from app.services.activity import ProjectActivityService


class ProjectSettingsService:
    """Reads and updates a project's environment/execution/security policy set."""

    def __init__(
        self, settings: ProjectSettingsRepository, activity: ProjectActivityService
    ) -> None:
        self._settings = settings
        self._activity = activity

    async def get_or_create(self, project_id: UUID, *, organization_id: UUID) -> ProjectSettings:
        """Return *project_id*'s settings, creating defaults if missing."""
        existing = await self._settings.get_for_project(project_id)
        if existing is not None:
            return existing
        return await self._settings.create(
            ProjectSettings(project_id=project_id, organization_id=organization_id)
        )

    async def update(
        self,
        project_id: UUID,
        *,
        organization_id: UUID,
        default_environment: str | None,
        default_connector_id: UUID | None,
        default_workflow_runtime: str | None,
        notification_settings: dict[str, Any],
        retention_policies: dict[str, Any],
        execution_policies: dict[str, Any],
        automation_policies: dict[str, Any],
        validation_policies: dict[str, Any],
        monitoring_policies: dict[str, Any],
        ai_settings: dict[str, Any],
        storage_policies: dict[str, Any],
        security_policies: dict[str, Any],
    ) -> ProjectSettings:
        """Update *project_id*'s settings ("Settings Updates")."""
        settings = await self.get_or_create(project_id, organization_id=organization_id)
        settings.default_environment = default_environment
        settings.default_connector_id = default_connector_id
        settings.default_workflow_runtime = default_workflow_runtime
        settings.notification_settings = notification_settings
        settings.retention_policies = retention_policies
        settings.execution_policies = execution_policies
        settings.automation_policies = automation_policies
        settings.validation_policies = validation_policies
        settings.monitoring_policies = monitoring_policies
        settings.ai_settings = ai_settings
        settings.storage_policies = storage_policies
        settings.security_policies = security_policies
        await self._activity.record(
            project_id,
            organization_id=organization_id,
            activity_type=ProjectActivityType.SETTINGS_UPDATED,
        )
        return settings


__all__ = ["ProjectSettingsService"]
