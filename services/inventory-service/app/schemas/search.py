"""Response schema for ``GET /inventory/search``."""

from __future__ import annotations

from pydantic import BaseModel

from app.schemas.asset import AssetResponse


class PaginationMetadataResponse(BaseModel):
    """One page's position within the full result set."""

    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_previous: bool


class AssetSearchResponse(BaseModel):
    """One page of asset search results."""

    items: list[AssetResponse]
    pagination: PaginationMetadataResponse


__all__ = ["AssetSearchResponse", "PaginationMetadataResponse"]
