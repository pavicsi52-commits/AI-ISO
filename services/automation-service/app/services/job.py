"""Automation job lifecycle: the definition-level orchestrator.

Per docs/040 "AUTOMATION TYPES"/"PLAYBOOK SUPPORT". Every create
publishes ``AutomationCreated``; a job's own ``status`` tracks its
enable/disable lifecycle, distinct from any one
:class:`~app.models.automation_execution.AutomationExecution`'s own
``status``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any
from uuid import UUID

from shared_core.database.filtering import Filter
from shared_core.database.pagination import PaginatedResult
from shared_core.database.sorting import SortField
from shared_core.events.base import DomainEvent

from app.events.automation_events import AutomationCreatedEvent
from app.models.automation_job import AutomationJob
from app.models.enums import AutomationType, ExecutionMode, JobStatus, PlaybookType
from app.repositories.automation_job import AutomationJobRepository
from app.services.audit import AutomationAuditService

EventPublisher = Callable[[DomainEvent], Awaitable[None]]


class AutomationJobService:
    """Creates, reads, updates, and deletes automation jobs."""

    def __init__(
        self,
        jobs: AutomationJobRepository,
        audit: AutomationAuditService,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._jobs = jobs
        self._audit = audit
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def get_by_id(self, job_id: UUID) -> AutomationJob:
        """Return the automation job identified by *job_id*.

        Raises:
            NotFoundError: If no such job exists.
        """
        return await self._jobs.require_by_id(job_id)

    async def list_for_org(self, organization_id: UUID) -> list[AutomationJob]:
        """Every automation job belonging to *organization_id*."""
        return await self._jobs.list_for_org(organization_id)

    async def search(
        self,
        *,
        query: str | None,
        filters: Sequence[Filter] | None,
        sort_fields: Sequence[SortField] | None,
        page: int | None,
        page_size: int | None,
    ) -> PaginatedResult[AutomationJob]:
        """Full-text search plus filter plus sort plus pagination."""
        return await self._jobs.search_and_paginate(
            query=query, filters=filters, sort_fields=sort_fields, page=page, page_size=page_size
        )

    async def create(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        name: str,
        description: str | None,
        automation_type: AutomationType,
        playbook_type: PlaybookType,
        execution_mode: ExecutionMode,
        content: str,
        target_selector: dict[str, Any],
        variables: dict[str, Any],
        tags: list[str],
        timeout_seconds: int | None,
        owner_id: UUID | None,
        created_by: UUID | None,
    ) -> AutomationJob:
        """Define a new automation job ("Create")."""
        job = await self._jobs.create(
            AutomationJob(
                organization_id=organization_id,
                project_id=project_id,
                name=name,
                description=description,
                automation_type=automation_type,
                playbook_type=playbook_type,
                status=JobStatus.ACTIVE,
                execution_mode=execution_mode,
                content=content,
                target_selector=target_selector,
                variables=variables,
                tags=tags,
                timeout_seconds=timeout_seconds,
                owner_id=owner_id,
            )
        )
        await self._audit.record(
            job_id=job.id,
            execution_id=None,
            organization_id=organization_id,
            actor_id=created_by,
            action="create",
            after={"name": name},
        )
        await self._publish(
            AutomationCreatedEvent(
                source_service="automation-service", payload={"job_id": str(job.id)}
            )
        )
        return job

    async def update(
        self,
        job_id: UUID,
        *,
        actor_id: UUID | None,
        name: str,
        description: str | None,
        status: JobStatus,
        automation_type: AutomationType,
        playbook_type: PlaybookType,
        execution_mode: ExecutionMode,
        content: str,
        target_selector: dict[str, Any],
        variables: dict[str, Any],
        tags: list[str],
        timeout_seconds: int | None,
        owner_id: UUID | None,
    ) -> AutomationJob:
        """Replace an automation job's mutable fields ("Update")."""
        job = await self.get_by_id(job_id)
        before = {"content": job.content, "status": str(job.status)}

        job.name = name
        job.description = description
        job.status = status
        job.automation_type = automation_type
        job.playbook_type = playbook_type
        job.execution_mode = execution_mode
        job.content = content
        job.target_selector = target_selector
        job.variables = variables
        job.tags = tags
        job.timeout_seconds = timeout_seconds
        job.owner_id = owner_id
        job = await self._jobs.update(job)

        await self._audit.record(
            job_id=job_id,
            execution_id=None,
            organization_id=job.organization_id,
            actor_id=actor_id,
            action="update",
            before=before,
            after={"content": content, "status": str(status)},
        )
        return job

    async def delete(self, job_id: UUID, *, actor_id: UUID | None) -> None:
        """Soft-delete an automation job ("Delete")."""
        job = await self.get_by_id(job_id)
        await self._jobs.delete(job_id)
        await self._audit.record(
            job_id=job_id,
            execution_id=None,
            organization_id=job.organization_id,
            actor_id=actor_id,
            action="delete",
        )


__all__ = ["AutomationJobService"]
