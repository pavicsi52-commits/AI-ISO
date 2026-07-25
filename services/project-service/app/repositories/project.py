"""Repository for :class:`app.models.project.Project`."""

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

from app.models.enums import ProjectStatus
from app.models.project import Project

_SEARCHABLE_FIELDS = ("name", "code", "description", "category")


class ProjectRepository(BaseRepository[Project]):
    """CRUD plus lookup for :class:`Project`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, Project, tenant_scope=tenant_scope)

    async def get_by_code(self, organization_id: UUID, code: str) -> Project | None:
        """Return the project identified by *code* within *organization_id*, or ``None``."""
        stmt = self._base_select().where(
            Project.organization_id == organization_id, Project.code == code
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_org(self, organization_id: UUID) -> list[Project]:
        """Every project belonging to *organization_id*."""
        stmt = self._base_select().where(Project.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_filtered(
        self,
        organization_id: UUID,
        *,
        status: ProjectStatus | None = None,
        category: str | None = None,
    ) -> list[Project]:
        """Every project in *organization_id*, optionally narrowed by
        *status*/*category* ("EXPORT": "Filtered Export").
        """
        stmt = self._base_select().where(Project.organization_id == organization_id)
        if status is not None:
            stmt = stmt.where(Project.status == status)
        if category is not None:
            stmt = stmt.where(Project.category == category)
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
    ) -> PaginatedResult[Project]:
        """Full-text search plus filter plus sort plus offset-pagination,
        combined. Per docs/034 "SEARCH": Project Name, Project Code, Tags,
        Labels, Owner, Status, Organization, Metadata, Full Text Search,
        Pagination, Sorting, Filtering -- *query* full-text-searches
        :data:`_SEARCHABLE_FIELDS`, *filters* narrows by any column
        (status/owner/organization directly; tags/labels via a joined
        subquery the caller passes as a
        :class:`~shared_core.database.filtering.Filter`), *sort_fields*
        orders, and the result is paginated. Mirrors
        ``services/user-management-service``'s identical
        ``UserRepository.search_and_paginate``.
        """
        stmt = self._base_select()
        if query:
            stmt = apply_search(stmt, Project, _SEARCHABLE_FIELDS, query, mode=SearchMode.ILIKE)
        if filters:
            stmt = apply_filters(stmt, Project, filters)
        if sort_fields:
            stmt = apply_sorting(stmt, Project, sort_fields)
        return await paginate_by_offset(self._session, stmt, page=page, page_size=page_size)


__all__ = ["ProjectRepository"]
