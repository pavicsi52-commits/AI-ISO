"""Department management. Per docs/033 "DEPARTMENTS": CRUD, Hierarchy,
Department Manager, Department Metadata.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from shared_core.events.base import DomainEvent

from app.events.organization_events import DepartmentCreatedEvent, DepartmentDeletedEvent
from app.models.department import Department
from app.models.enums import OrganizationActivityType
from app.repositories.department import DepartmentRepository
from app.services.activity import OrganizationActivityService

EventPublisher = Callable[[DomainEvent], Awaitable[None]]


class DepartmentService:
    """Creates, updates, deletes, and lists departments within an organization."""

    def __init__(
        self,
        departments: DepartmentRepository,
        activity: OrganizationActivityService,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._departments = departments
        self._activity = activity
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def get_by_id(self, department_id: UUID) -> Department:
        """Return the department identified by *department_id*.

        Raises:
            NotFoundError: If no such department exists.
        """
        return await self._departments.require_by_id(department_id)

    async def list_for_org(self, organization_id: UUID) -> list[Department]:
        """Every department in *organization_id* ("Department Management": list)."""
        return await self._departments.list_for_org(organization_id)

    async def create(
        self,
        organization_id: UUID,
        *,
        name: str,
        code: str,
        description: str | None,
        parent_department_id: UUID | None,
        manager_id: UUID | None,
        metadata: dict[str, Any],
    ) -> Department:
        """Create a new department ("Create")."""
        if parent_department_id is not None:
            await self._departments.require_by_id(parent_department_id)
        department = await self._departments.create(
            Department(
                organization_id=organization_id,
                name=name,
                code=code,
                description=description,
                parent_department_id=parent_department_id,
                manager_id=manager_id,
                metadata_=metadata,
            )
        )
        await self._activity.record(
            organization_id, activity_type=OrganizationActivityType.DEPARTMENT_CREATED
        )
        await self._publish(
            DepartmentCreatedEvent(
                source_service="organization-service",
                payload={"department_id": str(department.id)},
            )
        )
        return department

    async def update(
        self,
        department_id: UUID,
        *,
        name: str,
        description: str | None,
        parent_department_id: UUID | None,
        manager_id: UUID | None,
        metadata: dict[str, Any],
    ) -> Department:
        """Update a department's mutable fields ("Update")."""
        department = await self.get_by_id(department_id)
        if parent_department_id is not None and parent_department_id != department_id:
            await self._departments.require_by_id(parent_department_id)
        department.name = name
        department.description = description
        department.parent_department_id = parent_department_id
        department.manager_id = manager_id
        department.metadata_ = metadata
        return department

    async def delete(self, department_id: UUID) -> None:
        """Delete a department ("Delete")."""
        department = await self.get_by_id(department_id)
        organization_id = department.organization_id
        await self._departments.delete(department_id)
        await self._activity.record(
            organization_id, activity_type=OrganizationActivityType.DEPARTMENT_DELETED
        )
        await self._publish(
            DepartmentDeletedEvent(
                source_service="organization-service", payload={"department_id": str(department_id)}
            )
        )


__all__ = ["DepartmentService"]
