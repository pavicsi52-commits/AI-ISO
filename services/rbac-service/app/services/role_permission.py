"""Role/permission grant management.

Per docs/032 REST list: ``POST/DELETE /roles/{id}/permissions{,/{permissionId}}``.
"""

from __future__ import annotations

from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError

from app.constants import DEFAULT_ORGANIZATION_ID
from app.models.role_permission import RolePermission
from app.repositories.permission import PermissionRepository
from app.repositories.role import RoleRepository
from app.repositories.role_permission import RolePermissionRepository


class RolePermissionService:
    """Grants and revokes permissions on roles."""

    def __init__(
        self,
        role_permissions: RolePermissionRepository,
        roles: RoleRepository,
        permissions: PermissionRepository,
    ) -> None:
        self._role_permissions = role_permissions
        self._roles = roles
        self._permissions = permissions

    async def list_for_role(self, role_id: UUID) -> list[RolePermission]:
        """Every permission grant on *role_id*."""
        return await self._role_permissions.list_for_role(role_id)

    async def grant(
        self, role_id: UUID, permission_id: UUID, *, granted_by: UUID | None
    ) -> RolePermission:
        """Grant *permission_id* to *role_id* ("Assign").

        Raises:
            NotFoundError: If either does not exist.
            ConflictError: If already granted.
        """
        await self._roles.require_by_id(role_id)
        await self._permissions.require_by_id(permission_id)
        if await self._role_permissions.get(role_id, permission_id) is not None:
            raise ConflictError(f"Permission '{permission_id}' is already granted to this role.")
        return await self._role_permissions.create(
            RolePermission(
                role_id=role_id,
                permission_id=permission_id,
                granted_by=granted_by,
                organization_id=DEFAULT_ORGANIZATION_ID,
            )
        )

    async def revoke(self, role_id: UUID, permission_id: UUID) -> None:
        """Revoke *permission_id* from *role_id*.

        Raises:
            NotFoundError: If not currently granted.
        """
        grant = await self._role_permissions.get(role_id, permission_id)
        if grant is None:
            raise NotFoundError(f"Permission '{permission_id}' is not granted to role '{role_id}'.")
        await self._role_permissions.delete(grant.id)


__all__ = ["RolePermissionService"]
