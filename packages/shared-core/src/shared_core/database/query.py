"""Query Builder.

Per docs/018_Enterprise_Database_Framework.md.txt "QUERY BUILDER": AND, OR,
NOT, IN, BETWEEN, LIKE, ILIKE, JSONB, Full Text Search, Ordering, Grouping,
Aggregation, Subquery, Exists, Dynamic Filters. "Parameterized Queries
only" -- every method here builds a SQLAlchemy expression tree with bind
parameters; none ever formats a value into a SQL string.

:class:`QueryBuilder` is a thin fluent facade over
:mod:`~shared_core.database.filtering`, :mod:`~shared_core.database.sorting`,
and :mod:`~shared_core.database.search` -- it doesn't reimplement their
logic, it composes it with the lower-level AND/OR/NOT/IN/subquery
primitives that don't have a dedicated module of their own.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import Any, Literal, Self

from sqlalchemy import Select, and_, exists, func, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared_core.database.filtering import Filter, apply_filters
from shared_core.database.pagination import PaginatedResult, paginate_by_offset
from shared_core.database.search import SearchMode, apply_search
from shared_core.database.sorting import SortField, apply_sorting

_AggregateName = Literal["count", "sum", "avg", "min", "max"]
_AGGREGATE_FUNCTIONS: dict[_AggregateName, Callable[[Any], Any]] = {
    "count": func.count,
    "sum": func.sum,
    "avg": func.avg,
    "min": func.min,
    "max": func.max,
}


class QueryBuilder:
    """Fluent, parameterized query construction over one entity model."""

    def __init__(self, model: type[Any]) -> None:
        self._model = model
        self._stmt: Select[Any] = select(model)

    @property
    def statement(self) -> Select[Any]:
        """The underlying SQLAlchemy ``Select`` built up so far."""
        return self._stmt

    def where(self, *conditions: Any) -> Self:
        """AND-combine *conditions* into the statement's ``WHERE`` clause."""
        self._stmt = self._stmt.where(and_(*conditions))
        return self

    def where_any(self, *conditions: Any) -> Self:
        """OR-combine *conditions* into the statement's ``WHERE`` clause."""
        self._stmt = self._stmt.where(or_(*conditions))
        return self

    def where_not(self, condition: Any) -> Self:
        """Negate *condition* and add it to the ``WHERE`` clause."""
        self._stmt = self._stmt.where(not_(condition))
        return self

    def where_in(self, field: str, values: Iterable[Any]) -> Self:
        """Filter to rows where *field* is one of *values*."""
        column = getattr(self._model, field)
        self._stmt = self._stmt.where(column.in_(list(values)))
        return self

    def where_between(self, field: str, low: Any, high: Any) -> Self:
        """Filter to rows where *field* is between *low* and *high*, inclusive."""
        column = getattr(self._model, field)
        self._stmt = self._stmt.where(column.between(low, high))
        return self

    def like(self, field: str, pattern: str, *, case_insensitive: bool = True) -> Self:
        """Filter *field* against a caller-supplied LIKE/ILIKE *pattern*."""
        column = getattr(self._model, field)
        self._stmt = self._stmt.where(
            column.ilike(pattern) if case_insensitive else column.like(pattern)
        )
        return self

    def filters(self, filters: Sequence[Filter]) -> Self:
        """Apply a dynamic list of :class:`~shared_core.database.filtering.Filter` objects."""
        self._stmt = apply_filters(self._stmt, self._model, filters)
        return self

    def search(
        self, fields: Sequence[str], query: str, *, mode: SearchMode = SearchMode.ILIKE
    ) -> Self:
        """Apply full-text/ILIKE/trigram search across *fields*."""
        self._stmt = apply_search(self._stmt, self._model, fields, query, mode=mode)
        return self

    def order_by(self, sort_fields: Sequence[SortField]) -> Self:
        """Apply an ordered list of :class:`~shared_core.database.sorting.SortField` terms."""
        self._stmt = apply_sorting(self._stmt, self._model, sort_fields)
        return self

    def group_by(self, *fields: str) -> Self:
        """Group by the named columns."""
        columns = [getattr(self._model, field) for field in fields]
        self._stmt = self._stmt.group_by(*columns)
        return self

    def limit(self, value: int) -> Self:
        """Cap the number of returned rows."""
        self._stmt = self._stmt.limit(value)
        return self

    def offset(self, value: int) -> Self:
        """Skip the first *value* rows."""
        self._stmt = self._stmt.offset(value)
        return self

    def subquery(self) -> Any:
        """Return the current statement as a subquery, for use inside another query."""
        return self._stmt.subquery()

    def exists_clause(self) -> Any:
        """Return an ``EXISTS(...)`` clause for the current statement.

        For use as a condition in another query, e.g.
        ``other_builder.where(inner_builder.exists_clause())``.
        """
        return exists(self._stmt)

    def aggregate(self, field: str, *, agg: _AggregateName = "count") -> Select[Any]:
        """Build a standalone aggregate (count/sum/avg/min/max) query over *field*.

        Returns a fresh, independent ``Select`` (not chained onto this
        builder's own statement) -- an aggregate query has its own
        result shape and is executed separately.
        """
        column = getattr(self._model, field)
        return select(_AGGREGATE_FUNCTIONS[agg](column))

    async def count(self, session: AsyncSession) -> int:
        """Execute ``COUNT(*)`` over the current statement."""
        result = await session.execute(select(func.count()).select_from(self._stmt.subquery()))
        return result.scalar_one()

    async def all(self, session: AsyncSession) -> list[Any]:
        """Execute the current statement and return every matching entity."""
        result = await session.execute(self._stmt)
        return list(result.scalars().all())

    async def first(self, session: AsyncSession) -> Any | None:
        """Execute the current statement and return the first matching entity, if any."""
        result = await session.execute(self._stmt.limit(1))
        return result.scalars().first()

    async def paginate(
        self, session: AsyncSession, *, page: int | None = None, page_size: int | None = None
    ) -> PaginatedResult[Any]:
        """Execute the current statement as an offset-paginated page."""
        return await paginate_by_offset(session, self._stmt, page=page, page_size=page_size)


__all__ = ["QueryBuilder"]
