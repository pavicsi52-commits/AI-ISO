"""Shared sorting schema pieces."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from shared_core.schemas.base import BaseSchema


class SortOrder(StrEnum):
    """Sort direction."""

    ASC = "asc"
    DESC = "desc"


class SortParams(BaseSchema):
    """A single sort key and direction."""

    field: str = Field(min_length=1)
    order: SortOrder = SortOrder.ASC
