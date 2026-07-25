"""Role assignment: granting/removing a role on a user, at any scope.

Per docs/032 REST list: ``POST/DELETE /users/{id}/roles{,/{roleId}}``.
One role can be assigned to a user at the system, organization, or
project scope (``user_roles``/``organization_roles``/``project_roles``
respectively) -- this service is the single entry point routing to
whichever table ``scope_type`` names, so the REST layer doesn't need
three near-identical router pairs.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from shared_core.events.base import DomainEvent
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError

from app.constants import DEFAULT_ORGANIZATION_ID
from app.events.rbac_events import RoleAssignedEvent, RoleRemovedEvent
from app.models.enums import AssignmentStatus, SubjectType
from app.models.organization_role import OrganizationRole
from app.models.project_role import ProjectRole
from app.models.user_role import UserRole
from app.repositories.organization_role import OrganizationRoleRepository
from app.repositories.project_role import ProjectRoleRepository
from app.repositories.role import RoleRepository
from app.repositories.user_role import UserRoleRepository

EventPublisher = Callable[[DomainEvent], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class Assignment:
    """One role assignment, normalized across whichever table it lives in."""

    id: UUID
    user_id: UUID
    role_id: UUID
    scope_type: SubjectType
    scope_id: UUID | None
    status: AssignmentStatus
    assigned_by: UUID | None
    expires_at: datetime | None
    created_at: datetime


class RoleAssignmentService:
    """Assigns and removes roles on users, at any scope."""

    def __init__(
        self,
        user_roles: UserRoleRepository,
        organization_roles: OrganizationRoleRepository,
        project_roles: ProjectRoleRepository,
        roles: RoleRepository,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._user_roles = user_roles
        self._organization_roles = organization_roles
        self._project_roles = project_roles
        self._roles = roles
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def assign(
        self,
        user_id: UUID,
        role_id: UUID,
        *,
        scope_type: SubjectType,
        scope_id: UUID | None,
        expires_at: datetime | None,
        assigned_by: UUID | None,
    ) -> Assignment:
        """Assign *role_id* to *user_id* at *scope_type* ("Role Assignment").

        Raises:
            NotFoundError: If *role_id* does not exist.
            ConflictError: If already assigned at that exact scope.
            ValidationError: If *scope_type* needs a *scope_id* that's missing.
        """
        role = await self._roles.require_by_id(role_id)
        if scope_type == SubjectType.GLOBAL:
            if await self._user_roles.get(user_id, role_id) is not None:
                raise ConflictError(f"Role '{role.code}' is already assigned to this user.")
            record = await self._user_roles.create(
                UserRole(
                    user_id=user_id,
                    role_id=role_id,
                    assigned_by=assigned_by,
                    expires_at=expires_at,
                    organization_id=DEFAULT_ORGANIZATION_ID,
                )
            )
            assignment = _from_user_role(record)
        elif scope_type == SubjectType.ORGANIZATION:
            if scope_id is None:
                raise ValidationError("scope_id is required for an organization-scoped role.")
            existing = await self._organization_roles.get(user_id, role_id, scope_id)
            if existing is not None:
                raise ConflictError(f"Role '{role.code}' is already assigned in this organization.")
            org_record = await self._organization_roles.create(
                OrganizationRole(
                    user_id=user_id,
                    role_id=role_id,
                    assigned_by=assigned_by,
                    expires_at=expires_at,
                    organization_id=scope_id,
                )
            )
            assignment = _from_organization_role(org_record)
        elif scope_type == SubjectType.PROJECT:
            if scope_id is None:
                raise ValidationError("scope_id is required for a project-scoped role.")
            if await self._project_roles.get(user_id, role_id, scope_id) is not None:
                raise ConflictError(f"Role '{role.code}' is already assigned in this project.")
            project_record = await self._project_roles.create(
                ProjectRole(
                    user_id=user_id,
                    role_id=role_id,
                    assigned_by=assigned_by,
                    expires_at=expires_at,
                    project_id=scope_id,
                    organization_id=DEFAULT_ORGANIZATION_ID,
                )
            )
            assignment = _from_project_role(project_record)
        else:
            raise ValidationError(f"Unsupported role-assignment scope: {scope_type!r}.")

        await self._publish(
            RoleAssignedEvent(
                source_service="rbac-service",
                payload={"user_id": str(user_id), "role_id": str(role_id)},
            )
        )
        return assignment

    async def remove(
        self, user_id: UUID, role_id: UUID, *, scope_type: SubjectType, scope_id: UUID | None
    ) -> None:
        """Remove *role_id* from *user_id* at *scope_type*.

        Raises:
            NotFoundError: If no such assignment exists.
            ValidationError: If *scope_type* needs a *scope_id* that's missing.
        """
        if scope_type == SubjectType.GLOBAL:
            record = await self._user_roles.get(user_id, role_id)
            if record is None:
                raise NotFoundError("Role assignment was not found.")
            await self._user_roles.delete(record.id)
        elif scope_type == SubjectType.ORGANIZATION:
            if scope_id is None:
                raise ValidationError("scope_id is required for an organization-scoped role.")
            org_record = await self._organization_roles.get(user_id, role_id, scope_id)
            if org_record is None:
                raise NotFoundError("Role assignment was not found.")
            await self._organization_roles.delete(org_record.id)
        elif scope_type == SubjectType.PROJECT:
            if scope_id is None:
                raise ValidationError("scope_id is required for a project-scoped role.")
            project_record = await self._project_roles.get(user_id, role_id, scope_id)
            if project_record is None:
                raise NotFoundError("Role assignment was not found.")
            await self._project_roles.delete(project_record.id)
        else:
            raise ValidationError(f"Unsupported role-assignment scope: {scope_type!r}.")

        await self._publish(
            RoleRemovedEvent(
                source_service="rbac-service",
                payload={"user_id": str(user_id), "role_id": str(role_id)},
            )
        )

    async def list_for_user(self, user_id: UUID) -> list[Assignment]:
        """Every role *user_id* holds, across every scope ("Permission Aggregation")."""
        assignments = [_from_user_role(r) for r in await self._user_roles.list_for_user(user_id)]
        assignments += [
            _from_organization_role(r)
            for r in await self._organization_roles.list_for_user(user_id)
        ]
        assignments += [
            _from_project_role(r) for r in await self._project_roles.list_for_user(user_id)
        ]
        return assignments


def _from_user_role(record: UserRole) -> Assignment:
    return Assignment(
        id=record.id,
        user_id=record.user_id,
        role_id=record.role_id,
        scope_type=SubjectType.GLOBAL,
        scope_id=None,
        status=record.status,
        assigned_by=record.assigned_by,
        expires_at=record.expires_at,
        created_at=record.created_at,
    )


def _from_organization_role(record: OrganizationRole) -> Assignment:
    return Assignment(
        id=record.id,
        user_id=record.user_id,
        role_id=record.role_id,
        scope_type=SubjectType.ORGANIZATION,
        scope_id=record.organization_id,
        status=record.status,
        assigned_by=record.assigned_by,
        expires_at=record.expires_at,
        created_at=record.created_at,
    )


def _from_project_role(record: ProjectRole) -> Assignment:
    return Assignment(
        id=record.id,
        user_id=record.user_id,
        role_id=record.role_id,
        scope_type=SubjectType.PROJECT,
        scope_id=record.project_id,
        status=record.status,
        assigned_by=record.assigned_by,
        expires_at=record.expires_at,
        created_at=record.created_at,
    )


__all__ = ["Assignment", "RoleAssignmentService"]
