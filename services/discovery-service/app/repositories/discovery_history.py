"""Repository for :class:`app.models.discovery_history.DiscoveryHistoryEntry`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovery_history import DiscoveryHistoryEntry


class DiscoveryHistoryRepository(BaseRepository[DiscoveryHistoryEntry]):
    """CRUD plus lookup for :class:`DiscoveryHistoryEntry`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, DiscoveryHistoryEntry, tenant_scope=tenant_scope)

    async def list_for_job(self, job_id: UUID) -> list[DiscoveryHistoryEntry]:
        """Every narrative timeline entry for *job_id*, newest first."""
        stmt = (
            self._base_select()
            .where(DiscoveryHistoryEntry.job_id == job_id)
            .order_by(desc(DiscoveryHistoryEntry.created_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["DiscoveryHistoryRepository"]
