"""Request/response schemas for ``/users/notes``."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class NoteCreateRequest(BaseModel):
    """Body of ``POST /users/notes``."""

    body: str = Field(min_length=1, max_length=8192)


class NoteResponse(BaseModel):
    """One internal note."""

    id: UUID
    author_id: UUID
    body: str
    created_at: datetime


__all__ = ["NoteCreateRequest", "NoteResponse"]
