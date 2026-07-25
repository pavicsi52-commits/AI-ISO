"""Repository for :class:`app.models.asset_type.AssetTypeDefinition`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_type import AssetTypeDefinition


class AssetTypeDefinitionRepository(BaseRepository[AssetTypeDefinition]):
    """CRUD plus lookup for :class:`AssetTypeDefinition`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AssetTypeDefinition, tenant_scope=tenant_scope)

    async def get_by_code(self, organization_id: UUID, code: str) -> AssetTypeDefinition | None:
        """Return the type definition identified by *code* within
        *organization_id*, or ``None``.
        """
        stmt = self._base_select().where(
            AssetTypeDefinition.organization_id == organization_id,
            AssetTypeDefinition.code == code,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_org(self, organization_id: UUID) -> list[AssetTypeDefinition]:
        """Every type definition catalogued for *organization_id*."""
        stmt = self._base_select().where(AssetTypeDefinition.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AssetTypeDefinitionRepository"]
