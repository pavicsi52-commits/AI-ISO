"""Repository for :class:`app.models.discovery_job.DiscoveryJob`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovery_job import DiscoveryJob


class DiscoveryJobRepository(BaseRepository[DiscoveryJob]):
    """CRUD plus lookup for :class:`DiscoveryJob`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, DiscoveryJob, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[DiscoveryJob]:
        """Every discovery job for *organization_id*."""
        stmt = self._base_select().where(DiscoveryJob.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["DiscoveryJobRepository"]
