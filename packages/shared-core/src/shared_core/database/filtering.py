"""Filtering.

Per docs/018_Enterprise_Database_Framework.md.txt "FILTERING": Equal, Not
Equal, Greater Than, Less Than, Between, Contains, Starts With, Ends With,
Null, Not Null, Boolean, Date Range, JSONB. Every comparison is built with
SQLAlchemy's expression language against bind parameters -- "Parameterized
Queries only" (docs/018 "QUERY BUILDER"), never string interpolation.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from sqlalchemy import Select

from shared_core.database.helpers import build_like_pattern


class FilterOperator(StrEnum):
    """Supported filter comparison operators."""

    EQUAL = "eq"
    NOT_EQUAL = "ne"
    GREATER_THAN = "gt"
    GREATER_THAN_OR_EQUAL = "gte"
    LESS_THAN = "lt"
    LESS_THAN_OR_EQUAL = "lte"
    BETWEEN = "between"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"
    IS_TRUE = "is_true"
    IS_FALSE = "is_false"
    DATE_RANGE = "date_range"
    JSONB_CONTAINS = "jsonb_contains"
    JSONB_HAS_KEY = "jsonb_has_key"


_NULLARY_OPERATORS = frozenset(
    {
        FilterOperator.IS_NULL,
        FilterOperator.IS_NOT_NULL,
        FilterOperator.IS_TRUE,
        FilterOperator.IS_FALSE,
    }
)
_RANGE_OPERATORS = frozenset({FilterOperator.BETWEEN, FilterOperator.DATE_RANGE})

# Operators built from a single (column, value) pair with no other special
# shaping. Kept as a dispatch table (rather than an if/elif chain) so
# apply_filter stays under the branch-count a single function should have.
_BINARY_OPERATORS: dict[FilterOperator, Callable[[Any, Any], Any]] = {
    FilterOperator.EQUAL: lambda column, value: column == value,
    FilterOperator.NOT_EQUAL: lambda column, value: column != value,
    FilterOperator.GREATER_THAN: lambda column, value: column > value,
    FilterOperator.GREATER_THAN_OR_EQUAL: lambda column, value: column >= value,
    FilterOperator.LESS_THAN: lambda column, value: column < value,
    FilterOperator.LESS_THAN_OR_EQUAL: lambda column, value: column <= value,
    FilterOperator.CONTAINS: lambda column, value: column.ilike(build_like_pattern(str(value))),
    FilterOperator.STARTS_WITH: lambda column, value: column.ilike(
        build_like_pattern(str(value), anchor_start=True)
    ),
    FilterOperator.ENDS_WITH: lambda column, value: column.ilike(
        build_like_pattern(str(value), anchor_end=True)
    ),
    FilterOperator.JSONB_CONTAINS: lambda column, value: column.contains(value),
    FilterOperator.JSONB_HAS_KEY: lambda column, value: column.has_key(value),
}

# Operators that take no value at all -- built from the column alone.
_NULLARY_CONDITIONS: dict[FilterOperator, Callable[[Any], Any]] = {
    FilterOperator.IS_NULL: lambda column: column.is_(None),
    FilterOperator.IS_NOT_NULL: lambda column: column.is_not(None),
    FilterOperator.IS_TRUE: lambda column: column.is_(True),
    FilterOperator.IS_FALSE: lambda column: column.is_(False),
}


@dataclass(frozen=True, slots=True)
class Filter:
    """One field filter: ``field <operator> value[, value2]``."""

    field: str
    operator: FilterOperator
    value: Any = None
    value2: Any = None

    def __post_init__(self) -> None:
        if self.operator in _RANGE_OPERATORS and self.value2 is None:
            raise ValueError(f"Filter operator {self.operator!r} requires both value and value2.")
        is_shaped = self.operator in _NULLARY_OPERATORS or self.operator in _RANGE_OPERATORS
        if not is_shaped and self.value is None:
            raise ValueError(f"Filter operator {self.operator!r} requires a value.")


def apply_filter(stmt: Select[Any], model: type[Any], filter_: Filter) -> Select[Any]:
    """Apply a single :class:`Filter` to *stmt* as a ``WHERE`` clause."""
    column = getattr(model, filter_.field)
    op = filter_.operator

    if op in _NULLARY_CONDITIONS:
        return stmt.where(_NULLARY_CONDITIONS[op](column))
    if op in _RANGE_OPERATORS:
        return stmt.where(column.between(filter_.value, filter_.value2))
    if op in _BINARY_OPERATORS:
        return stmt.where(_BINARY_OPERATORS[op](column, filter_.value))

    raise ValueError(f"Unsupported filter operator: {op!r}")  # pragma: no cover -- exhaustive above


def apply_filters(stmt: Select[Any], model: type[Any], filters: Sequence[Filter]) -> Select[Any]:
    """Apply every :class:`Filter` in *filters* to *stmt*, AND-combined."""
    for filter_ in filters:
        stmt = apply_filter(stmt, model, filter_)
    return stmt


__all__ = ["Filter", "FilterOperator", "apply_filter", "apply_filters"]
