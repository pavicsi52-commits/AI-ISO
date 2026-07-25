"""Repository for :class:`app.models.organization_quota.OrganizationQuota`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization_quota import OrganizationQuota


class OrganizationQuotaRepository(BaseRepository[OrganizationQuota]):
    """CRUD plus lookup for :class:`OrganizationQuota`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, OrganizationQuota, tenant_scope=tenant_scope)

    async def get_for_org(self, organization_id: UUID) -> OrganizationQuota | None:
        """Return *organization_id*'s quota row, or ``None``."""
        stmt = self._base_select().where(OrganizationQuota.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["OrganizationQuotaRepository"]
