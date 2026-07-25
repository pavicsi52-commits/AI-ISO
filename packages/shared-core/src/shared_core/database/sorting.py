"""Sorting.

Per docs/018_Enterprise_Database_Framework.md.txt "SORTING": Ascending,
Descending, Multiple Fields, Null First, Null Last.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from sqlalchemy import Select


class SortDirection(StrEnum):
    """Sort direction for one field."""

    ASC = "asc"
    DESC = "desc"


class NullsPosition(StrEnum):
    """Where ``NULL`` values sort relative to non-null ones."""

    FIRST = "first"
    LAST = "last"


@dataclass(frozen=True, slots=True)
class SortField:
    """One ``ORDER BY`` term."""

    field: str
    direction: SortDirection = SortDirection.ASC
    nulls: NullsPosition | None = None


_NULLS_TOKEN_INDEX = 2


def apply_sorting(
    stmt: Select[Any], model: type[Any], sort_fields: Sequence[SortField]
) -> Select[Any]:
    """Apply every :class:`SortField` in *sort_fields* to *stmt*, in order given."""
    for sort_field in sort_fields:
        column = getattr(model, sort_field.field)
        ordering = column.asc() if sort_field.direction is SortDirection.ASC else column.desc()
        if sort_field.nulls is NullsPosition.FIRST:
            ordering = ordering.nulls_first()
        elif sort_field.nulls is NullsPosition.LAST:
            ordering = ordering.nulls_last()
        stmt = stmt.order_by(ordering)
    return stmt


def parse_sort_expression(raw: str | None) -> list[SortField]:
    """Parse a querystring sort expression into :class:`SortField` objects.

    Format: comma-separated ``field[:asc|desc[:nulls_first|nulls_last]]``
    terms, e.g. ``"created_at:desc:nulls_last,name:asc"``. A bare field name
    defaults to ascending with the database's default null ordering.
    """
    if not raw:
        return []

    fields: list[SortField] = []
    for raw_term in raw.split(","):
        term = raw_term.strip()
        if not term:
            continue
        parts = [p.strip() for p in term.split(":")]
        name = parts[0]
        direction = SortDirection.ASC
        if len(parts) > 1 and parts[1].lower() == "desc":
            direction = SortDirection.DESC
        nulls: NullsPosition | None = None
        if len(parts) > _NULLS_TOKEN_INDEX:
            nulls_token = parts[_NULLS_TOKEN_INDEX].lower()
            if nulls_token in ("nulls_first", "first"):
                nulls = NullsPosition.FIRST
            elif nulls_token in ("nulls_last", "last"):
                nulls = NullsPosition.LAST
        fields.append(SortField(field=name, direction=direction, nulls=nulls))
    return fields


__all__ = [
    "NullsPosition",
    "SortDirection",
    "SortField",
    "apply_sorting",
    "parse_sort_expression",
]
