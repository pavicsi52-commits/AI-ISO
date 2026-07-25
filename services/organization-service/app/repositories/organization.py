"""Repository for :class:`app.models.organization.Organization`."""

from __future__ import annotations

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization


class OrganizationRepository(BaseRepository[Organization]):
    """CRUD plus lookup for :class:`Organization`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, Organization, tenant_scope=tenant_scope)

    async def get_by_slug(self, slug: str) -> Organization | None:
        """Return the organization identified by *slug*, or ``None``."""
        stmt = self._base_select().where(Organization.slug == slug)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self) -> list[Organization]:
        """Every organization ("Organization Management": list)."""
        result = await self._session.execute(self._base_select())
        return list(result.scalars().all())


__all__ = ["OrganizationRepository"]
