"""Project activity tracking.

Per docs/034's own "DATABASE TABLES" list: ``project_activity`` is this
service's narrative "what happened and why" feed, mirroring
``services/organization-service``'s identical ``OrganizationActivityService``
shape one tenant level down.

**A genuine second-tenant-level nuance**: every entity in this service
carries both the mandatory (inherited) ``organization_id`` column and
this service's own ``project_id`` foreign key. Unlike
organization-service (where a row's ``organization_id`` *is* its own
scope), every child row here needs its owning project's
``organization_id`` propagated explicitly -- callers that already hold
the parent :class:`~app.models.project.Project` (as every caller of
this service does) pass it straight through.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.enums import ProjectActivityType
from app.models.project_activity import ProjectActivity
from app.repositories.project_activity import ProjectActivityRepository


class ProjectActivityService:
    """Records and lists project-activity feed entries."""

    def __init__(self, activity: ProjectActivityRepository) -> None:
        self._activity = activity

    async def record(
        self,
        project_id: UUID,
        *,
        organization_id: UUID,
        activity_type: ProjectActivityType,
        actor_id: UUID | None = None,
        description: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> ProjectActivity:
        """Record one activity event ("Track ...")."""
        return await self._activity.create(
            ProjectActivity(
                project_id=project_id,
                organization_id=organization_id,
                actor_id=actor_id,
                activity_type=activity_type,
                description=description,
                detail=detail or {},
            )
        )

    async def list_recent(self, project_id: UUID, *, limit: int = 50) -> list[ProjectActivity]:
        """The *limit* most recent activity entries for *project_id*."""
        return await self._activity.list_recent_for_project(project_id, limit=limit)


__all__ = ["ProjectActivityService"]
