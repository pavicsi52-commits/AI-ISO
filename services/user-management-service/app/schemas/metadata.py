"""Request/response schemas for ``/users/metadata``."""

from __future__ import annotations

from pydantic import BaseModel, Field


class MetadataSetRequest(BaseModel):
    """Body of ``PUT /users/metadata/{key}``."""

    value: str = Field(max_length=4096)


class MetadataEntryResponse(BaseModel):
    """One key/value metadata entry."""

    key: str
    value: str


__all__ = ["MetadataEntryResponse", "MetadataSetRequest"]
