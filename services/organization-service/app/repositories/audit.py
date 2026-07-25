"""Repository for :class:`app.models.audit.OrganizationAuditEntry`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import OrganizationAuditEntry


class OrganizationAuditRepository(BaseRepository[OrganizationAuditEntry]):
    """CRUD plus listing for :class:`OrganizationAuditEntry`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, OrganizationAuditEntry, tenant_scope=tenant_scope)

    async def list_recent_for_org(
        self, organization_id: UUID, *, limit: int = 50
    ) -> list[OrganizationAuditEntry]:
        """The *limit* most recent audit entries for *organization_id*, newest first."""
        stmt = (
            self._base_select()
            .where(OrganizationAuditEntry.organization_id == organization_id)
            .order_by(desc(OrganizationAuditEntry.created_at))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["OrganizationAuditRepository"]
