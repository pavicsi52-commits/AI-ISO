"""Request/response schemas for ``/users/tags``."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class TagCreateRequest(BaseModel):
    """Body of ``POST /users/tags``."""

    label: str = Field(max_length=64)
    category: str | None = Field(default=None, max_length=64)


class TagResponse(BaseModel):
    """One tag assignment."""

    id: UUID
    label: str
    category: str | None


__all__ = ["TagCreateRequest", "TagResponse"]
