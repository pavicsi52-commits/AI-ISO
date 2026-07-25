"""Project management.

Per docs/034 "PROJECT MODEL"/"PROJECT LIFECYCLE": Create, Clone,
Archive, Restore, Export, Import, Transfer Ownership, Soft Delete,
Permanent Delete. The tenant "root" entity of this service -- its own
``project_id`` column is set equal to its own ``id`` at creation, the
same self-referential pattern ``services/organization-service``
established for its own ``organization_id`` one tenant level up (see
``app/models/project.py``'s own docstring).

Creating a project also provisions its default settings/preferences
rows, matching ``services/organization-service``'s own ``create()``
shape -- but *not* the creator's own Owner membership, which the API
layer adds separately (:class:`~app.services.member.ProjectMemberService`
needs the caller's id, which this service has no reason to know).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.database.filtering import Filter
from shared_core.database.pagination import PaginatedResult
from shared_core.database.sorting import SortField
from shared_core.events.base import DomainEvent
from shared_core.exceptions.conflict import ConflictError

from app.events.project_events import (
    ProjectArchivedEvent,
    ProjectClonedEvent,
    ProjectCreatedEvent,
    ProjectDeletedEvent,
    ProjectOwnershipTransferredEvent,
    ProjectRestoredEvent,
    ProjectUpdatedEvent,
)
from app.models.enums import ProjectActivityType, ProjectPriority, ProjectStatus, ProjectVisibility
from app.models.project import Project
from app.models.project_preferences import ProjectPreferences
from app.models.project_settings import ProjectSettings
from app.repositories.project import ProjectRepository
from app.repositories.project_preferences import ProjectPreferencesRepository
from app.repositories.project_settings import ProjectSettingsRepository
from app.services.activity import ProjectActivityService
from app.services.archive import ProjectArchiveService

EventPublisher = Callable[[DomainEvent], Awaitable[None]]


class ProjectService:
    """Creates, updates, deletes, and transitions the lifecycle of projects."""

    def __init__(
        self,
        projects: ProjectRepository,
        settings: ProjectSettingsRepository,
        preferences: ProjectPreferencesRepository,
        activity: ProjectActivityService,
        archives: ProjectArchiveService,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._projects = projects
        self._settings = settings
        self._preferences = preferences
        self._activity = activity
        self._archives = archives
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def get_by_id(self, project_id: UUID) -> Project:
        """Return the project identified by *project_id*.

        Raises:
            NotFoundError: If no such project exists.
        """
        return await self._projects.require_by_id(project_id)

    async def list_for_org(self, organization_id: UUID) -> list[Project]:
        """Every project belonging to *organization_id*."""
        return await self._projects.list_for_org(organization_id)

    async def search(
        self,
        *,
        query: str | None,
        filters: Sequence[Filter] | None,
        sort_fields: Sequence[SortField] | None,
        page: int | None,
        page_size: int | None,
    ) -> PaginatedResult[Project]:
        """Full-text search plus filter plus sort plus pagination ("SEARCH")."""
        return await self._projects.search_and_paginate(
            query=query, filters=filters, sort_fields=sort_fields, page=page, page_size=page_size
        )

    async def create(
        self,
        *,
        organization_id: UUID,
        owner_id: UUID,
        name: str,
        code: str,
        display_name: str | None,
        description: str | None,
        visibility: ProjectVisibility,
        default_language: str,
        timezone: str,
        category: str | None,
        priority: ProjectPriority,
        metadata: dict[str, Any],
    ) -> Project:
        """Create a new project, with its default child rows ("Create").

        Raises:
            ConflictError: If *code* is already taken within *organization_id*.
        """
        if await self._projects.get_by_code(organization_id, code) is not None:
            raise ConflictError(f"Project code {code!r} is already taken in this organization.")

        project_id = uuid.uuid4()
        project = await self._projects.create(
            Project(
                id=project_id,
                project_id=project_id,
                organization_id=organization_id,
                name=name,
                code=code,
                display_name=display_name,
                description=description,
                status=ProjectStatus.DRAFT,
                owner_id=owner_id,
                visibility=visibility,
                default_language=default_language,
                timezone=timezone,
                category=category,
                priority=priority,
                metadata_=metadata,
            )
        )
        await self._settings.create(
            ProjectSettings(project_id=project_id, organization_id=organization_id)
        )
        await self._preferences.create(
            ProjectPreferences(project_id=project_id, organization_id=organization_id)
        )

        await self._activity.record(
            project_id,
            organization_id=organization_id,
            actor_id=owner_id,
            activity_type=ProjectActivityType.PROJECT_CREATED,
        )
        await self._publish(
            ProjectCreatedEvent(
                source_service="project-service", payload={"project_id": str(project_id)}
            )
        )
        return project

    async def update(
        self,
        project_id: UUID,
        *,
        name: str,
        display_name: str | None,
        description: str | None,
        status: ProjectStatus,
        visibility: ProjectVisibility,
        default_language: str,
        timezone: str,
        category: str | None,
        priority: ProjectPriority,
        metadata: dict[str, Any],
    ) -> Project:
        """Replace a project's mutable fields ("Update")."""
        project = await self.get_by_id(project_id)
        project.name = name
        project.display_name = display_name
        project.description = description
        project.status = status
        project.visibility = visibility
        project.default_language = default_language
        project.timezone = timezone
        project.category = category
        project.priority = priority
        project.metadata_ = metadata
        return await self._finish_update(project)

    async def patch(
        self,
        project_id: UUID,
        *,
        name: str | None = None,
        display_name: str | None = None,
        description: str | None = None,
        status: ProjectStatus | None = None,
        visibility: ProjectVisibility | None = None,
        default_language: str | None = None,
        timezone: str | None = None,
        category: str | None = None,
        priority: ProjectPriority | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Project:
        """Update only the given, non-``None`` fields ("PATCH partial update")."""
        project = await self.get_by_id(project_id)
        if name is not None:
            project.name = name
        if display_name is not None:
            project.display_name = display_name
        if description is not None:
            project.description = description
        if status is not None:
            project.status = status
        if visibility is not None:
            project.visibility = visibility
        if default_language is not None:
            project.default_language = default_language
        if timezone is not None:
            project.timezone = timezone
        if category is not None:
            project.category = category
        if priority is not None:
            project.priority = priority
        if metadata is not None:
            project.metadata_ = metadata
        return await self._finish_update(project)

    async def _finish_update(self, project: Project) -> Project:
        await self._activity.record(
            project.id,
            organization_id=project.organization_id,
            activity_type=ProjectActivityType.PROJECT_UPDATED,
        )
        await self._publish(
            ProjectUpdatedEvent(
                source_service="project-service", payload={"project_id": str(project.id)}
            )
        )
        return project

    async def delete(self, project_id: UUID) -> None:
        """Soft-delete a project ("Soft Delete")."""
        project = await self.get_by_id(project_id)
        await self._projects.delete(project_id)
        await self._publish(
            ProjectDeletedEvent(
                source_service="project-service", payload={"project_id": str(project.id)}
            )
        )

    async def clone(self, project_id: UUID, *, name: str, code: str, cloned_by: UUID) -> Project:
        """Clone a project's identity fields into a brand-new project ("Clone").

        Raises:
            ConflictError: If *code* is already taken within the source
                project's organization.
        """
        source = await self.get_by_id(project_id)
        clone = await self.create(
            organization_id=source.organization_id,
            owner_id=cloned_by,
            name=name,
            code=code,
            display_name=source.display_name,
            description=source.description,
            visibility=source.visibility,
            default_language=source.default_language,
            timezone=source.timezone,
            category=source.category,
            priority=source.priority,
            metadata=dict(source.metadata_),
        )
        await self._activity.record(
            clone.id,
            organization_id=clone.organization_id,
            actor_id=cloned_by,
            activity_type=ProjectActivityType.PROJECT_CLONED,
            detail={"source_project_id": str(project_id)},
        )
        await self._publish(
            ProjectClonedEvent(
                source_service="project-service",
                payload={"project_id": str(clone.id), "source_project_id": str(project_id)},
            )
        )
        return clone

    async def archive(
        self, project_id: UUID, *, archived_by: UUID | None, reason: str | None
    ) -> Project:
        """Archive a project ("Archive")."""
        project = await self.get_by_id(project_id)
        project.status = ProjectStatus.ARCHIVED
        project.archived_at = datetime.now(UTC)
        await self._archives.record_archive(
            project_id,
            organization_id=project.organization_id,
            archived_by=archived_by,
            reason=reason,
            snapshot={"status": str(project.status), "name": project.name},
        )
        await self._activity.record(
            project_id,
            organization_id=project.organization_id,
            actor_id=archived_by,
            activity_type=ProjectActivityType.PROJECT_ARCHIVED,
        )
        await self._publish(
            ProjectArchivedEvent(
                source_service="project-service", payload={"project_id": str(project_id)}
            )
        )
        return project

    async def restore(self, project_id: UUID, *, restored_by: UUID | None) -> Project:
        """Restore an archived project ("Restore").

        Raises:
            NotFoundError: If *project_id* has no unrestored archive event.
        """
        project = await self.get_by_id(project_id)
        await self._archives.record_restore(project_id, restored_by=restored_by)
        project.status = ProjectStatus.ACTIVE
        project.archived_at = None
        await self._activity.record(
            project_id,
            organization_id=project.organization_id,
            actor_id=restored_by,
            activity_type=ProjectActivityType.PROJECT_RESTORED,
        )
        await self._publish(
            ProjectRestoredEvent(
                source_service="project-service", payload={"project_id": str(project_id)}
            )
        )
        return project

    async def set_owner(self, project_id: UUID, *, new_owner_id: UUID) -> Project:
        """Set *project_id*'s authoritative ``owner_id`` field ("Transfer
        Ownership"). Membership-row bookkeeping (promoting the new owner's
        role, demoting the previous owner's) is a separate concern the API
        layer orchestrates via
        :class:`~app.services.member.ProjectMemberService.transfer_ownership`,
        the same "cross-service-object orchestration lives at the API
        layer" pattern ``POST /organizations`` established for creating a
        organization plus its owner membership together.
        """
        project = await self.get_by_id(project_id)
        project.owner_id = new_owner_id
        await self._activity.record(
            project_id,
            organization_id=project.organization_id,
            actor_id=new_owner_id,
            activity_type=ProjectActivityType.OWNERSHIP_TRANSFERRED,
        )
        await self._publish(
            ProjectOwnershipTransferredEvent(
                source_service="project-service", payload={"project_id": str(project_id)}
            )
        )
        return project


__all__ = ["ProjectService"]
