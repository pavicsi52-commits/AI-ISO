"""Request/response schemas for playbook tags."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class PlaybookTagCreateRequest(BaseModel):
    """Body of ``POST /playbooks/{id}/tags``."""

    tag: str = Field(min_length=1, max_length=100)


class PlaybookTagResponse(BaseModel):
    """One tag assigned to a playbook."""

    id: UUID
    playbook_id: UUID
    tag: str


__all__ = ["PlaybookTagCreateRequest", "PlaybookTagResponse"]
