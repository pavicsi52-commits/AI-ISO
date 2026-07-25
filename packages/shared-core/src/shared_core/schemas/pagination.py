"""Shared pagination schema pieces."""

from __future__ import annotations

from pydantic import Field, model_validator

from shared_core.constants import HttpConstants
from shared_core.schemas.base import BaseSchema


class PaginationParams(BaseSchema):
    """Page/page-size pair used by every list endpoint."""

    page: int = Field(default=HttpConstants.DEFAULT_PAGE, ge=1)
    page_size: int = Field(
        default=HttpConstants.DEFAULT_PAGE_SIZE,
        ge=1,
        le=HttpConstants.MAX_PAGE_SIZE,
    )

    @property
    def offset(self) -> int:
        """Zero-based row offset for this page."""
        return (self.page - 1) * self.page_size


class PaginationMeta(BaseSchema):
    """Pagination metadata returned alongside a page of results."""

    page: int
    page_size: int
    total: int
    has_next: bool
    has_previous: bool

    @model_validator(mode="after")
    def _check_flags_consistent(self) -> PaginationMeta:
        expected_has_previous = self.page > 1
        if self.has_previous != expected_has_previous:
            raise ValueError("has_previous is inconsistent with page")
        return self

    @classmethod
    def from_params(cls, params: PaginationParams, total: int) -> PaginationMeta:
        """Build pagination metadata from the request params and a total count."""
        last_page = max(1, -(-total // params.page_size))  # ceil division
        return cls(
            page=params.page,
            page_size=params.page_size,
            total=total,
            has_next=params.page < last_page,
            has_previous=params.page > 1,
        )
