"""Role management.

Per docs/032 "ROLE MANAGEMENT"/"ROLE HIERARCHY": Create, Update,
Delete, Inheritance, Circular Dependency Detection. Delegates the pure
hierarchy algorithms to :mod:`app.roles.hierarchy` -- this service is
the persistence/orchestration layer around them.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from shared_core.events.base import DomainEvent
from shared_core.exceptions.business import BusinessRuleError
from shared_core.exceptions.not_found import NotFoundError

from app.constants import DEFAULT_ORGANIZATION_ID
from app.events.rbac_events import RoleCreatedEvent, RoleDeletedEvent, RoleUpdatedEvent
from app.models.enums import RoleStatus, RoleType
from app.models.role import Role
from app.repositories.role import RoleRepository
from app.repositories.role_permission import RolePermissionRepository
from app.roles.hierarchy import RoleNode, aggregate_permission_ids, would_create_cycle

EventPublisher = Callable[[DomainEvent], Awaitable[None]]


class RoleService:
    """Creates, updates, deletes, and resolves the hierarchy of roles."""

    def __init__(
        self,
        roles: RoleRepository,
        role_permissions: RolePermissionRepository,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._roles = roles
        self._role_permissions = role_permissions
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def get_by_id(self, role_id: UUID) -> Role:
        """Return the role identified by *role_id*.

        Raises:
            NotFoundError: If no such role exists.
        """
        return await self._roles.require_by_id(role_id)

    async def list_all(self) -> list[Role]:
        """Every role ("Role Management": list)."""
        return await self._roles.list_all()

    async def create(
        self,
        *,
        name: str,
        code: str,
        description: str | None,
        role_type: RoleType,
        parent_role_id: UUID | None,
        priority: int,
        project_id: UUID | None,
        metadata: dict[str, Any],
    ) -> Role:
        """Create a new role ("Create").

        Raises:
            BusinessRuleError: If *parent_role_id* would create a cycle.
        """
        if parent_role_id is not None:
            await self._roles.require_by_id(parent_role_id)
        role = await self._roles.create(
            Role(
                name=name,
                code=code,
                description=description,
                role_type=role_type,
                parent_role_id=parent_role_id,
                priority=priority,
                project_id=project_id,
                metadata_=metadata,
                organization_id=DEFAULT_ORGANIZATION_ID,
            )
        )
        await self._publish(
            RoleCreatedEvent(source_service="rbac-service", payload={"role_id": str(role.id)})
        )
        return role

    async def update(
        self,
        role_id: UUID,
        *,
        name: str,
        description: str | None,
        status: RoleStatus,
        parent_role_id: UUID | None,
        priority: int,
        metadata: dict[str, Any],
    ) -> Role:
        """Update a role's mutable fields ("Update").

        Raises:
            BusinessRuleError: If *parent_role_id* would create a cycle.
        """
        role = await self.get_by_id(role_id)
        if parent_role_id is not None and parent_role_id != role.parent_role_id:
            await self._require_no_cycle(role_id=role_id, new_parent_id=parent_role_id)
        role.name = name
        role.description = description
        role.status = status
        role.parent_role_id = parent_role_id
        role.priority = priority
        role.metadata_ = metadata
        await self._publish(
            RoleUpdatedEvent(source_service="rbac-service", payload={"role_id": str(role.id)})
        )
        return role

    async def delete(self, role_id: UUID) -> None:
        """Soft-delete a role ("Delete").

        Raises:
            BusinessRuleError: If the role is a protected system role.
        """
        role = await self.get_by_id(role_id)
        if role.is_system:
            raise BusinessRuleError(f"System role '{role.code}' cannot be deleted.")
        await self._roles.delete(role_id)
        await self._publish(
            RoleDeletedEvent(source_service="rbac-service", payload={"role_id": str(role_id)})
        )

    async def resolve_effective_permission_ids(self, role_id: UUID) -> set[UUID]:
        """Every permission id *role_id* holds, directly or via inheritance
        ("Permission Aggregation", "Recursive Evaluation").
        """
        all_roles = await self._roles.list_all()
        graph = {r.id: RoleNode(id=r.id, parent_role_id=r.parent_role_id) for r in all_roles}
        role_permission_ids: dict[UUID, list[UUID]] = {}
        for r in all_roles:
            grants = await self._role_permissions.list_for_role(r.id)
            role_permission_ids[r.id] = [g.permission_id for g in grants]
        return aggregate_permission_ids(graph, role_permission_ids, role_id)

    async def _require_no_cycle(self, *, role_id: UUID, new_parent_id: UUID) -> None:
        all_roles = await self._roles.list_all()
        graph = {r.id: RoleNode(id=r.id, parent_role_id=r.parent_role_id) for r in all_roles}
        if new_parent_id not in graph:
            raise NotFoundError(f"Role '{new_parent_id}' was not found.")
        if would_create_cycle(graph, role_id, new_parent_id):
            raise BusinessRuleError(
                f"Setting role {role_id}'s parent to {new_parent_id} would create a circular "
                "role hierarchy."
            )


__all__ = ["RoleService"]
