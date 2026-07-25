"""Repository for :class:`app.models.resource_permission.ResourcePermission`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ResourceType, SubjectType
from app.models.resource_permission import ResourcePermission


class ResourcePermissionRepository(BaseRepository[ResourcePermission]):
    """CRUD plus lookup for :class:`ResourcePermission`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ResourcePermission, tenant_scope=tenant_scope)

    async def list_for_resource(
        self, resource_type: ResourceType, resource_id: UUID
    ) -> list[ResourcePermission]:
        """Every direct grant/deny recorded on *resource_type*/*resource_id*."""
        stmt = self._base_select().where(
            ResourcePermission.resource_type == resource_type,
            ResourcePermission.resource_id == resource_id,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_subject(
        self, subject_type: SubjectType, subject_id: UUID
    ) -> list[ResourcePermission]:
        """Every direct grant/deny held by *subject_type*/*subject_id*."""
        stmt = self._base_select().where(
            ResourcePermission.subject_type == subject_type,
            ResourcePermission.subject_id == subject_id,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ResourcePermissionRepository"]
