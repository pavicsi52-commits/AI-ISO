"""Project resource linking. Per docs/034 "PROJECT RESOURCES": tracks
every infrastructure resource, inventory asset, workflow, automation
job, connector, AI agent, report, dashboard, etc. a project owns.

No dedicated REST surface is named in docs/034's own endpoint list --
this service exists for programmatic completeness, the same scope
decision ``app/services/preferences.py`` documents.
"""

from __future__ import annotations

from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError

from app.models.enums import ProjectActivityType, ProjectResourceType
from app.models.project_resource import ProjectResource
from app.repositories.project_resource import ProjectResourceRepository
from app.services.activity import ProjectActivityService


class ProjectResourceService:
    """Links, lists, and unlinks external resources on a project."""

    def __init__(
        self, resources: ProjectResourceRepository, activity: ProjectActivityService
    ) -> None:
        self._resources = resources
        self._activity = activity

    async def list_for_project(self, project_id: UUID) -> list[ProjectResource]:
        """Every resource linked to *project_id*."""
        return await self._resources.list_for_project(project_id)

    async def link(
        self,
        project_id: UUID,
        *,
        organization_id: UUID,
        resource_type: ProjectResourceType,
        resource_id: UUID,
        name: str | None,
        linked_by: UUID | None,
    ) -> ProjectResource:
        """Link an external resource to *project_id* ("Resource Linking").

        Raises:
            ConflictError: If this exact resource is already linked.
        """
        if await self._resources.get_by_link(project_id, resource_type, resource_id) is not None:
            raise ConflictError("This resource is already linked to the project.")
        resource = await self._resources.create(
            ProjectResource(
                project_id=project_id,
                organization_id=organization_id,
                resource_type=resource_type,
                resource_id=resource_id,
                name=name,
                linked_by=linked_by,
            )
        )
        await self._activity.record(
            project_id,
            organization_id=organization_id,
            actor_id=linked_by,
            activity_type=ProjectActivityType.RESOURCE_LINKED,
        )
        return resource

    async def unlink(
        self, project_id: UUID, resource_link_id: UUID, *, organization_id: UUID
    ) -> None:
        """Remove a resource link.

        Raises:
            NotFoundError: If no such link exists for *project_id*.
        """
        record = await self._resources.require_by_id(resource_link_id)
        if record.project_id != project_id:
            raise NotFoundError(
                f"Resource link '{resource_link_id}' was not found for this project."
            )
        await self._resources.delete(resource_link_id)
        await self._activity.record(
            project_id,
            organization_id=organization_id,
            activity_type=ProjectActivityType.RESOURCE_UNLINKED,
        )


__all__ = ["ProjectResourceService"]
