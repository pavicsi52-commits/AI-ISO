"""Request/response schemas for playbook labels."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class PlaybookLabelCreateRequest(BaseModel):
    """Body of ``POST /playbooks/{id}/labels``."""

    key: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=512)


class PlaybookLabelResponse(BaseModel):
    """One key/value label assigned to a playbook."""

    id: UUID
    playbook_id: UUID
    key: str
    value: str


__all__ = ["PlaybookLabelCreateRequest", "PlaybookLabelResponse"]
