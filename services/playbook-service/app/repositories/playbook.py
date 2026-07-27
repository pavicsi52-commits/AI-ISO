"""Repository for :class:`app.models.playbook.Playbook`."""

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

from app.models.enums import PlaybookStatus
from app.models.playbook import Playbook

_SEARCHABLE_FIELDS = ("name", "display_name", "description")


class PlaybookRepository(BaseRepository[Playbook]):
    """CRUD plus lookup/search/pagination for :class:`Playbook`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, Playbook, tenant_scope=tenant_scope)

    async def list_for_org(
        self, organization_id: UUID, *, status: PlaybookStatus | None = None
    ) -> list[Playbook]:
        """Every playbook belonging to *organization_id*, optionally
        narrowed to a single *status*.
        """
        stmt = self._base_select().where(Playbook.organization_id == organization_id)
        if status is not None:
            stmt = stmt.where(Playbook.status == status)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_repository(self, repository_id: UUID) -> list[Playbook]:
        """Every playbook filed under *repository_id*."""
        stmt = self._base_select().where(Playbook.repository_id == repository_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_name(self, organization_id: UUID, name: str) -> list[Playbook]:
        """Every playbook in *organization_id* named exactly *name*
        (dependency names aren't required to be unique)."""
        stmt = self._base_select().where(
            Playbook.organization_id == organization_id, Playbook.name == name
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
    ) -> PaginatedResult[Playbook]:
        """Full-text search plus filter plus sort plus offset-pagination, combined."""
        stmt = self._base_select()
        if query:
            stmt = apply_search(stmt, Playbook, _SEARCHABLE_FIELDS, query, mode=SearchMode.ILIKE)
        if filters:
            stmt = apply_filters(stmt, Playbook, filters)
        if sort_fields:
            stmt = apply_sorting(stmt, Playbook, sort_fields)
        return await paginate_by_offset(self._session, stmt, page=page, page_size=page_size)


__all__ = ["PlaybookRepository"]
