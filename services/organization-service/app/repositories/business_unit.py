"""Repository for :class:`app.models.business_unit.BusinessUnit`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business_unit import BusinessUnit


class BusinessUnitRepository(BaseRepository[BusinessUnit]):
    """CRUD plus lookup/hierarchy queries for :class:`BusinessUnit`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, BusinessUnit, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[BusinessUnit]:
        """Every business unit belonging to *organization_id*."""
        stmt = self._base_select().where(BusinessUnit.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_children(self, parent_business_unit_id: UUID) -> list[BusinessUnit]:
        """Every business unit whose ``parent_business_unit_id`` matches."""
        stmt = self._base_select().where(
            BusinessUnit.parent_business_unit_id == parent_business_unit_id
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["BusinessUnitRepository"]
