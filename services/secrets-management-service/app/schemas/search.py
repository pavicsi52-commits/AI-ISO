"""Response schema for ``GET /secrets/search``."""

from __future__ import annotations

from pydantic import BaseModel

from app.schemas.secret import SecretSummaryResponse


class PaginationMetadataResponse(BaseModel):
    """One page's position within the full result set."""

    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_previous: bool


class SecretSearchResponse(BaseModel):
    """One page of secret search results. Never carries decrypted values --
    see ``app/schemas/secret.py``'s module docstring.
    """

    items: list[SecretSummaryResponse]
    pagination: PaginationMetadataResponse


__all__ = ["PaginationMetadataResponse", "SecretSearchResponse"]
