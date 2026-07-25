"""Repository for :class:`app.models.asset.Asset`."""

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

from app.models.asset import Asset

_SEARCHABLE_FIELDS = (
    "name",
    "hostname",
    "fqdn",
    "ip_address",
    "mac_address",
    "serial_number",
    "vendor",
    "model",
    "operating_system",
)


class AssetRepository(BaseRepository[Asset]):
    """CRUD plus lookup/search/pagination for :class:`Asset`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, Asset, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[Asset]:
        """Every asset belonging to *organization_id*."""
        stmt = self._base_select().where(Asset.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_hostname(self, organization_id: UUID, hostname: str) -> Asset | None:
        """Return the asset identified by *hostname* within *organization_id*, or ``None``."""
        stmt = self._base_select().where(
            Asset.organization_id == organization_id, Asset.hostname == hostname
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_serial_number(self, organization_id: UUID, serial_number: str) -> Asset | None:
        """Return the asset identified by *serial_number* within
        *organization_id*, or ``None`` -- used to "Prevent duplicate
        identifiers" ("SECURITY").
        """
        stmt = self._base_select().where(
            Asset.organization_id == organization_id, Asset.serial_number == serial_number
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_mac_address(self, organization_id: UUID, mac_address: str) -> Asset | None:
        """Return the asset identified by *mac_address* within *organization_id*, or ``None``."""
        stmt = self._base_select().where(
            Asset.organization_id == organization_id, Asset.mac_address == mac_address
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def search_and_paginate(
        self,
        *,
        query: str | None = None,
        filters: Sequence[Filter] | None = None,
        sort_fields: Sequence[SortField] | None = None,
        page: int | None = None,
        page_size: int | None = None,
    ) -> PaginatedResult[Asset]:
        """Full-text search plus filter plus sort plus offset-pagination,
        combined. Per docs/036 "SEARCH": Hostname, IP Address, MAC
        Address, Serial Number, Vendor, Model, OS, Tags, Labels,
        Metadata, Owner, Project, Organization, Full Text Search,
        Pagination, Sorting, Filtering.
        """
        stmt = self._base_select()
        if query:
            stmt = apply_search(stmt, Asset, _SEARCHABLE_FIELDS, query, mode=SearchMode.ILIKE)
        if filters:
            stmt = apply_filters(stmt, Asset, filters)
        if sort_fields:
            stmt = apply_sorting(stmt, Asset, sort_fields)
        return await paginate_by_offset(self._session, stmt, page=page, page_size=page_size)


__all__ = ["AssetRepository"]
