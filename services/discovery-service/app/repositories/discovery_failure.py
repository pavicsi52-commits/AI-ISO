"""Repository for :class:`app.models.discovery_failure.DiscoveryFailure`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovery_failure import DiscoveryFailure


class DiscoveryFailureRepository(BaseRepository[DiscoveryFailure]):
    """CRUD plus lookup for :class:`DiscoveryFailure`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, DiscoveryFailure, tenant_scope=tenant_scope)

    async def list_for_job(self, job_id: UUID) -> list[DiscoveryFailure]:
        """Every failed probe recorded for *job_id*."""
        stmt = self._base_select().where(DiscoveryFailure.job_id == job_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["DiscoveryFailureRepository"]
