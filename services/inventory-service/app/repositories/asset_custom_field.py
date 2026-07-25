"""Repository for :class:`app.models.asset_custom_field.AssetCustomField`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_custom_field import AssetCustomField


class AssetCustomFieldRepository(BaseRepository[AssetCustomField]):
    """CRUD plus lookup for :class:`AssetCustomField`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AssetCustomField, tenant_scope=tenant_scope)

    async def get_by_name(self, organization_id: UUID, name: str) -> AssetCustomField | None:
        """Return the field definition identified by *name* within
        *organization_id*, or ``None``.
        """
        stmt = self._base_select().where(
            AssetCustomField.organization_id == organization_id, AssetCustomField.name == name
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_org(self, organization_id: UUID) -> list[AssetCustomField]:
        """Every custom field definition available in *organization_id*."""
        stmt = self._base_select().where(AssetCustomField.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AssetCustomFieldRepository"]
