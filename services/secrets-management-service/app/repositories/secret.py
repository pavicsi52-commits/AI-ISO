"""Repository for :class:`app.models.secret.Secret`."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from shared_core.database.filtering import Filter, apply_filters
from shared_core.database.pagination import PaginatedResult, paginate_by_offset
from shared_core.database.repository import BaseRepository
from shared_core.database.search import SearchMode, apply_search
from shared_core.database.sorting import SortField, apply_sorting
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import SecretStatus
from app.models.secret import Secret

_SEARCHABLE_FIELDS = ("name", "description")


class SecretRepository(BaseRepository[Secret]):
    """CRUD plus lookup/search/pagination for :class:`Secret`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, Secret, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[Secret]:
        """Every secret belonging to *organization_id*."""
        stmt = self._base_select().where(Secret.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_expiring_before(self, cutoff: datetime) -> list[Secret]:
        """Every still-``ACTIVE`` secret with an :attr:`~Secret.expires_at`
        before *cutoff* -- used by the background expiry worker to find
        both already-expired secrets (``cutoff=now``) and secrets
        expiring soon (``cutoff=now + warning_window``).
        """
        stmt = self._base_select().where(
            Secret.status == SecretStatus.ACTIVE,
            Secret.expires_at.is_not(None),
            Secret.expires_at < cutoff,
        )
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
    ) -> PaginatedResult[Secret]:
        """Full-text search plus filter plus sort plus offset-pagination,
        combined. Per docs/035 "SECRET SEARCH": Name, Category, Tags, Owner,
        Status, Provider, Metadata, Pagination, Sorting, Filtering.
        """
        stmt = self._base_select()
        if query:
            stmt = apply_search(stmt, Secret, _SEARCHABLE_FIELDS, query, mode=SearchMode.ILIKE)
        if filters:
            stmt = apply_filters(stmt, Secret, filters)
        if sort_fields:
            stmt = apply_sorting(stmt, Secret, sort_fields)
        return await paginate_by_offset(self._session, stmt, page=page, page_size=page_size)


__all__ = ["SecretRepository"]
