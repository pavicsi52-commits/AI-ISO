"""Repository for :class:`app.models.organization_branding.OrganizationBranding`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization_branding import OrganizationBranding


class OrganizationBrandingRepository(BaseRepository[OrganizationBranding]):
    """CRUD plus lookup for :class:`OrganizationBranding`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, OrganizationBranding, tenant_scope=tenant_scope)

    async def get_for_org(self, organization_id: UUID) -> OrganizationBranding | None:
        """Return *organization_id*'s branding row, or ``None``."""
        stmt = self._base_select().where(OrganizationBranding.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["OrganizationBrandingRepository"]
