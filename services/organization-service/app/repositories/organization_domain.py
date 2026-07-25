"""Repository for :class:`app.models.organization_domain.OrganizationDomain`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization_domain import OrganizationDomain


class OrganizationDomainRepository(BaseRepository[OrganizationDomain]):
    """CRUD plus lookup for :class:`OrganizationDomain`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, OrganizationDomain, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[OrganizationDomain]:
        """Every domain claimed by *organization_id*."""
        stmt = self._base_select().where(OrganizationDomain.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_domain(self, domain: str) -> OrganizationDomain | None:
        """Return the claim for *domain* (globally unique), or ``None``."""
        stmt = self._base_select().where(OrganizationDomain.domain == domain)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["OrganizationDomainRepository"]
