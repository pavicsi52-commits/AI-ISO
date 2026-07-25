"""Repository for :class:`app.models.organization_metadata.OrganizationMetadataEntry`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization_metadata import OrganizationMetadataEntry


class OrganizationMetadataRepository(BaseRepository[OrganizationMetadataEntry]):
    """CRUD plus lookup for :class:`OrganizationMetadataEntry`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, OrganizationMetadataEntry, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[OrganizationMetadataEntry]:
        """Every metadata entry for *organization_id*."""
        stmt = self._base_select().where(
            OrganizationMetadataEntry.organization_id == organization_id
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_key(self, organization_id: UUID, key: str) -> OrganizationMetadataEntry | None:
        """Return *organization_id*'s metadata entry for *key*, or ``None``."""
        stmt = self._base_select().where(
            OrganizationMetadataEntry.organization_id == organization_id,
            OrganizationMetadataEntry.key == key,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["OrganizationMetadataRepository"]
