"""Permission group management. Per docs/032 "PERMISSION GROUPS"."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.constants import DEFAULT_ORGANIZATION_ID
from app.models.enums import PermissionGroupCategory
from app.models.permission_group import PermissionGroup
from app.repositories.permission_group import PermissionGroupRepository


class PermissionGroupService:
    """Creates and lists permission groups."""

    def __init__(self, groups: PermissionGroupRepository) -> None:
        self._groups = groups

    async def get_by_id(self, group_id: UUID) -> PermissionGroup:
        """Return the permission group identified by *group_id*.

        Raises:
            NotFoundError: If no such permission group exists.
        """
        return await self._groups.require_by_id(group_id)

    async def list_all(self) -> list[PermissionGroup]:
        """Every permission group."""
        return await self._groups.list_all()

    async def create(
        self,
        *,
        name: str,
        code: str,
        description: str | None,
        category: PermissionGroupCategory,
        metadata: dict[str, Any],
    ) -> PermissionGroup:
        """Create a new permission group ("Custom Groups")."""
        return await self._groups.create(
            PermissionGroup(
                name=name,
                code=code,
                description=description,
                category=category,
                metadata_=metadata,
                organization_id=DEFAULT_ORGANIZATION_ID,
            )
        )


__all__ = ["PermissionGroupService"]
