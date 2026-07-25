"""Repository for :class:`app.models.automation_job.AutomationJob`."""

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

from app.models.automation_job import AutomationJob

_SEARCHABLE_FIELDS = ("name", "description")


class AutomationJobRepository(BaseRepository[AutomationJob]):
    """CRUD plus lookup/search/pagination for :class:`AutomationJob`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AutomationJob, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[AutomationJob]:
        """Every automation job belonging to *organization_id*."""
        stmt = self._base_select().where(AutomationJob.organization_id == organization_id)
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
    ) -> PaginatedResult[AutomationJob]:
        """Full-text search plus filter plus sort plus offset-pagination, combined."""
        stmt = self._base_select()
        if query:
            stmt = apply_search(
                stmt, AutomationJob, _SEARCHABLE_FIELDS, query, mode=SearchMode.ILIKE
            )
        if filters:
            stmt = apply_filters(stmt, AutomationJob, filters)
        if sort_fields:
            stmt = apply_sorting(stmt, AutomationJob, sort_fields)
        return await paginate_by_offset(self._session, stmt, page=page, page_size=page_size)


__all__ = ["AutomationJobRepository"]
