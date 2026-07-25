"""Repository for :class:`app.models.user.User`.

The first real consumer in this codebase of
:mod:`shared_core.database.search`/``filtering``/``pagination``
end-to-end together (per docs/031 "USER SEARCH": Username, Email,
Phone, Department, Status, Tags, Metadata, Full Text Search,
Pagination, Sorting, Filtering) -- ``BaseRepository.search()``/
``.paginate()`` each cover only half of that (search XOR filter+sort+
paginate), so :meth:`UserRepository.search_and_paginate` composes the
underlying primitives directly.
"""

from __future__ import annotations

from collections.abc import Sequence

from shared_core.database.filtering import Filter, apply_filters
from shared_core.database.pagination import PaginatedResult, paginate_by_offset
from shared_core.database.repository import BaseRepository
from shared_core.database.search import SearchMode, apply_search
from shared_core.database.sorting import SortField, apply_sorting
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

_SEARCHABLE_FIELDS = ("username", "email", "phone_number", "display_name")


class UserRepository(BaseRepository[User]):
    """CRUD plus lookup/search/pagination for :class:`User`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, User, tenant_scope=tenant_scope)

    async def get_by_username(self, username: str) -> User | None:
        """Return the user with *username*, or ``None``."""
        stmt = self._base_select().where(User.username == username)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        """Return the user with *email*, or ``None``."""
        stmt = self._base_select().where(User.email == email)
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
    ) -> PaginatedResult[User]:
        """Full-text search plus filter plus sort plus offset-pagination, combined.

        Covers docs/031 "USER SEARCH" in full: *query* full-text-searches
        :data:`_SEARCHABLE_FIELDS`, *filters* narrows by any column
        (status, department via ``UserProfile`` is a join the caller
        composes separately, tags/metadata via a joined subquery the
        caller passes as a :class:`~shared_core.database.filtering.Filter`
        on this table), *sort_fields* orders, and the result is paginated.
        """
        stmt = self._base_select()
        if query:
            stmt = apply_search(stmt, User, _SEARCHABLE_FIELDS, query, mode=SearchMode.FULL_TEXT)
        if filters:
            stmt = apply_filters(stmt, User, filters)
        if sort_fields:
            stmt = apply_sorting(stmt, User, sort_fields)
        return await paginate_by_offset(self._session, stmt, page=page, page_size=page_size)


__all__ = ["UserRepository"]
