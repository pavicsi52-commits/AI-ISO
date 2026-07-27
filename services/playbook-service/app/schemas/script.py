"""Request/response schemas for playbook auxiliary script files."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ContentType


class PlaybookScriptCreateRequest(BaseModel):
    """Body of ``POST /playbooks/{id}/scripts``."""

    file_name: str = Field(min_length=1, max_length=255)
    script_type: ContentType
    content: str = Field(min_length=1)
    is_entry_point: bool = False


class PlaybookScriptResponse(BaseModel):
    """One auxiliary content file bundled with a playbook."""

    id: UUID
    playbook_id: UUID
    file_name: str
    script_type: ContentType
    content: str
    is_entry_point: bool


__all__ = ["PlaybookScriptCreateRequest", "PlaybookScriptResponse"]
