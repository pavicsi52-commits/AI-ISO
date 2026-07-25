"""Repository for :class:`app.models.discovery_audit.DiscoveryAuditEntry`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovery_audit import DiscoveryAuditEntry


class DiscoveryAuditRepository(BaseRepository[DiscoveryAuditEntry]):
    """CRUD plus lookup for :class:`DiscoveryAuditEntry`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, DiscoveryAuditEntry, tenant_scope=tenant_scope)

    async def list_for_job(self, job_id: UUID) -> list[DiscoveryAuditEntry]:
        """Every audit entry for *job_id*, newest first."""
        stmt = (
            self._base_select()
            .where(DiscoveryAuditEntry.job_id == job_id)
            .order_by(desc(DiscoveryAuditEntry.created_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["DiscoveryAuditRepository"]
