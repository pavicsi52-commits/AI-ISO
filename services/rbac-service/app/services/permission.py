"""Permission management. Per docs/032 "PERMISSION MANAGEMENT"."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from shared_core.events.base import DomainEvent
from shared_core.security.rbac import PermissionScope

from app.constants import DEFAULT_ORGANIZATION_ID
from app.events.rbac_events import (
    PermissionCreatedEvent,
    PermissionDeletedEvent,
    PermissionUpdatedEvent,
)
from app.models.enums import PermissionAction, PermissionStatus, ResourceType
from app.models.permission import Permission
from app.repositories.permission import PermissionRepository

EventPublisher = Callable[[DomainEvent], Awaitable[None]]


class PermissionService:
    """Creates, updates, deletes, and lists permissions."""

    def __init__(
        self, permissions: PermissionRepository, *, publish_event: EventPublisher | None = None
    ) -> None:
        self._permissions = permissions
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def get_by_id(self, permission_id: UUID) -> Permission:
        """Return the permission identified by *permission_id*.

        Raises:
            NotFoundError: If no such permission exists.
        """
        return await self._permissions.require_by_id(permission_id)

    async def list_all(self) -> list[Permission]:
        """Every permission ("Permission Management": list)."""
        return await self._permissions.list_all()

    async def create(
        self,
        *,
        name: str,
        code: str,
        description: str | None,
        category: str | None,
        resource: ResourceType,
        action: PermissionAction,
        scope: PermissionScope,
        permission_group_id: UUID | None,
        metadata: dict[str, Any],
    ) -> Permission:
        """Create a new permission ("Create")."""
        permission = await self._permissions.create(
            Permission(
                name=name,
                code=code,
                description=description,
                category=category,
                resource=resource,
                action=action,
                scope=scope,
                permission_group_id=permission_group_id,
                metadata_=metadata,
                organization_id=DEFAULT_ORGANIZATION_ID,
            )
        )
        await self._publish(
            PermissionCreatedEvent(
                source_service="rbac-service", payload={"permission_id": str(permission.id)}
            )
        )
        return permission

    async def update(
        self,
        permission_id: UUID,
        *,
        name: str,
        description: str | None,
        category: str | None,
        status: PermissionStatus,
        permission_group_id: UUID | None,
        metadata: dict[str, Any],
    ) -> Permission:
        """Update a permission's mutable fields ("Update")."""
        permission = await self.get_by_id(permission_id)
        permission.name = name
        permission.description = description
        permission.category = category
        permission.status = status
        permission.permission_group_id = permission_group_id
        permission.metadata_ = metadata
        permission.version += 1
        await self._publish(
            PermissionUpdatedEvent(
                source_service="rbac-service", payload={"permission_id": str(permission.id)}
            )
        )
        return permission

    async def delete(self, permission_id: UUID) -> None:
        """Soft-delete a permission ("Delete")."""
        await self.get_by_id(permission_id)
        await self._permissions.delete(permission_id)
        await self._publish(
            PermissionDeletedEvent(
                source_service="rbac-service", payload={"permission_id": str(permission_id)}
            )
        )


__all__ = ["PermissionService"]
