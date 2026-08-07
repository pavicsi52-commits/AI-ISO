"""``connector_sync_jobs`` repository."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import SyncStatus
from app.models.sync import ConnectorSyncJob


class ConnectorSyncJobRepository(BaseRepository[ConnectorSyncJob]):
    """Synchronization runs."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ConnectorSyncJob, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, sync_job_id: UUID) -> ConnectorSyncJob:
        """One sync job by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(ConnectorSyncJob.organization_id == organization_id)
            .where(ConnectorSyncJob.id == sync_job_id)
        )
        result = await self._session.execute(stmt)
        found: ConnectorSyncJob | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No sync job with id {sync_job_id} in this organization.")
        return found

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        connector_id: UUID | None = None,
        status: SyncStatus | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[ConnectorSyncJob]:
        """Sync jobs in this organization, newest first."""
        stmt = self._base_select().where(ConnectorSyncJob.organization_id == organization_id)
        if connector_id is not None:
            stmt = stmt.where(ConnectorSyncJob.connector_id == connector_id)
        if status is not None:
            stmt = stmt.where(ConnectorSyncJob.status == str(status))
        stmt = stmt.order_by(ConnectorSyncJob.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_pending(self, *, limit: int = 500) -> list[ConnectorSyncJob]:
        """Every pending sync job across every organization -- for the sync scheduler sweep."""
        stmt = (
            self._base_select()
            .where(ConnectorSyncJob.status == str(SyncStatus.PENDING))
            .order_by(ConnectorSyncJob.created_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ConnectorSyncJobRepository"]
