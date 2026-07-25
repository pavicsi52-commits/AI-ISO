"""Repository for :class:`app.models.managed_asset.ManagedAsset`."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from shared_core.database.filtering import Filter, apply_filters
from shared_core.database.pagination import PaginatedResult, paginate_by_offset
from shared_core.database.repository import BaseRepository
from shared_core.database.search import SearchMode, apply_search
from shared_core.database.sorting import SortField, apply_sorting
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.managed_asset import ManagedAsset

_SEARCHABLE_FIELDS = ("business_name",)


class ManagedAssetRepository(BaseRepository[ManagedAsset]):
    """CRUD plus lookup/search/pagination for :class:`ManagedAsset`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ManagedAsset, tenant_scope=tenant_scope)

    async def get_by_inventory_asset_id(self, inventory_asset_id: UUID) -> ManagedAsset | None:
        """Return the managed asset governing *inventory_asset_id*, or ``None``."""
        stmt = self._base_select().where(ManagedAsset.inventory_asset_id == inventory_asset_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_org(self, organization_id: UUID) -> list[ManagedAsset]:
        """Every managed asset belonging to *organization_id*."""
        stmt = self._base_select().where(ManagedAsset.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def search_and_paginate(
        self,
        *,
        query: str | None = None,
        filters: Sequence[Filter] | None = None,
        sort_fields: Sequence[SortField] | None = None,
        page: int | None = None,
        page_size: int | None = None,
    ) -> PaginatedResult[ManagedAsset]:
        """Full-text search plus filter plus sort plus offset-pagination, combined."""
        stmt = self._base_select()
        if query:
            stmt = apply_search(
                stmt, ManagedAsset, _SEARCHABLE_FIELDS, query, mode=SearchMode.ILIKE
            )
        if filters:
            stmt = apply_filters(stmt, ManagedAsset, filters)
        if sort_fields:
            stmt = apply_sorting(stmt, ManagedAsset, sort_fields)
        return await paginate_by_offset(self._session, stmt, page=page, page_size=page_size)


__all__ = ["ManagedAssetRepository"]
