"""Response schema for ``GET /projects/search``."""

from __future__ import annotations

from pydantic import BaseModel

from app.schemas.project import ProjectResponse


class PaginationMetadataResponse(BaseModel):
    """One page's position within the full result set."""

    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_previous: bool


class ProjectSearchResponse(BaseModel):
    """One page of project search results."""

    items: list[ProjectResponse]
    pagination: PaginationMetadataResponse


__all__ = ["PaginationMetadataResponse", "ProjectSearchResponse"]
