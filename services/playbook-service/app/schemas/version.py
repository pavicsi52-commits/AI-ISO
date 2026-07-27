"""Request/response schemas for ``/playbooks/{id}/versions``."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PlaybookVersionCreateRequest(BaseModel):
    """Body of ``POST /playbooks/{id}/versions``."""

    content: str = Field(min_length=1)
    release_notes: str | None = None
    change_summary: str | None = Field(default=None, max_length=2048)
    changed_by: UUID | None = None


class PlaybookVersionResponse(BaseModel):
    """One immutable content snapshot of a playbook."""

    id: UUID
    playbook_id: UUID
    version_number: str
    content: str
    checksum: str
    release_notes: str | None
    change_summary: str | None
    changed_by: UUID | None
    approved_by: UUID | None
    approved_at: datetime | None
    created_at: datetime


__all__ = ["PlaybookVersionCreateRequest", "PlaybookVersionResponse"]
