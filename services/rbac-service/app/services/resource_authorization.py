"""Resource-instance authorization grants.

Per docs/032 "RESOURCE AUTHORIZATION". No REST surface is named for
this in docs/032's own endpoint list -- this service exists to back
:class:`app.evaluators.authorization_evaluator.AuthorizationEvaluator`'s
resource-ownership/sharing checks, consulted internally rather than
administered directly over HTTP in this prompt's scope.
"""

from __future__ import annotations

from uuid import UUID

from app.constants import DEFAULT_ORGANIZATION_ID
from app.models.enums import PolicyEffect, ResourceType, SubjectType
from app.models.resource_permission import ResourcePermission
from app.repositories.resource_permission import ResourcePermissionRepository


class ResourceAuthorizationService:
    """Reads the direct grants recorded on a resource instance."""

    def __init__(self, resource_permissions: ResourcePermissionRepository) -> None:
        self._resource_permissions = resource_permissions

    async def grants_for_resource(
        self, resource_type: ResourceType, resource_id: UUID
    ) -> list[ResourcePermission]:
        """Every direct grant/deny recorded on *resource_type*/*resource_id*
        ("Resource Owner", "Shared Resources", "Public Resources").
        """
        return await self._resource_permissions.list_for_resource(resource_type, resource_id)

    async def grant(
        self,
        *,
        resource_type: ResourceType,
        resource_id: UUID,
        subject_type: SubjectType,
        subject_id: UUID,
        permission_id: UUID,
        is_owner: bool,
        is_public: bool,
        granted_by: UUID | None,
    ) -> ResourcePermission:
        """Record a direct allow grant on one resource instance."""
        return await self._resource_permissions.create(
            ResourcePermission(
                resource_type=resource_type,
                resource_id=resource_id,
                subject_type=subject_type,
                subject_id=subject_id,
                permission_id=permission_id,
                effect=PolicyEffect.ALLOW,
                is_owner=is_owner,
                is_public=is_public,
                granted_by=granted_by,
                organization_id=DEFAULT_ORGANIZATION_ID,
            )
        )


__all__ = ["ResourceAuthorizationService"]
