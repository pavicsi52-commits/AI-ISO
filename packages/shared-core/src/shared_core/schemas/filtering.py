"""Shared filtering schema pieces."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field

from shared_core.schemas.base import BaseSchema


class FilterOperator(StrEnum):
    """Comparison operator for a single filter clause."""

    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    BETWEEN = "between"
    IN = "in"


class FilterParams(BaseSchema):
    """A single filter clause: field, operator, and comparison value(s)."""

    field: str = Field(min_length=1)
    operator: FilterOperator
    value: Any = None
