"""Repository for :class:`app.models.discovery_result.DiscoveryResult`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovery_result import DiscoveryResult


class DiscoveryResultRepository(BaseRepository[DiscoveryResult]):
    """CRUD plus lookup for :class:`DiscoveryResult`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, DiscoveryResult, tenant_scope=tenant_scope)

    async def list_for_job(self, job_id: UUID) -> list[DiscoveryResult]:
        """Every probe result recorded for *job_id*."""
        stmt = self._base_select().where(DiscoveryResult.job_id == job_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_target(self, target_id: UUID) -> list[DiscoveryResult]:
        """Every probe result recorded for *target_id*, across all jobs."""
        stmt = self._base_select().where(DiscoveryResult.target_id == target_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["DiscoveryResultRepository"]
