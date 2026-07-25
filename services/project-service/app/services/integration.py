"""Project integration management -- no dedicated REST surface in
docs/034's own endpoint list, matching ``app/services/preferences.py``'s
identical scope decision.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError

from app.models.project_integration import ProjectIntegration
from app.repositories.project_integration import ProjectIntegrationRepository


class ProjectIntegrationService:
    """Configures, lists, and removes a project's external-system integrations."""

    def __init__(self, integrations: ProjectIntegrationRepository) -> None:
        self._integrations = integrations

    async def list_for_project(self, project_id: UUID) -> list[ProjectIntegration]:
        """Every integration configured for *project_id*."""
        return await self._integrations.list_for_project(project_id)

    async def create(
        self,
        project_id: UUID,
        *,
        organization_id: UUID,
        name: str,
        integration_type: str,
        external_reference_id: UUID | None,
        config: dict[str, Any],
    ) -> ProjectIntegration:
        """Configure a new integration for *project_id*.

        Raises:
            ConflictError: If an integration named *name* already exists.
        """
        if await self._integrations.get_by_name(project_id, name) is not None:
            raise ConflictError(f"An integration named {name!r} already exists on this project.")
        return await self._integrations.create(
            ProjectIntegration(
                project_id=project_id,
                organization_id=organization_id,
                name=name,
                integration_type=integration_type,
                external_reference_id=external_reference_id,
                config=config,
            )
        )

    async def set_enabled(
        self, project_id: UUID, integration_id: UUID, *, is_enabled: bool
    ) -> ProjectIntegration:
        """Enable or disable an integration.

        Raises:
            NotFoundError: If no such integration exists for *project_id*.
        """
        record = await self._integrations.require_by_id(integration_id)
        if record.project_id != project_id:
            raise NotFoundError(f"Integration '{integration_id}' was not found for this project.")
        record.is_enabled = is_enabled
        return record

    async def remove(self, project_id: UUID, integration_id: UUID) -> None:
        """Remove an integration.

        Raises:
            NotFoundError: If no such integration exists for *project_id*.
        """
        record = await self._integrations.require_by_id(integration_id)
        if record.project_id != project_id:
            raise NotFoundError(f"Integration '{integration_id}' was not found for this project.")
        await self._integrations.delete(integration_id)


__all__ = ["ProjectIntegrationService"]
