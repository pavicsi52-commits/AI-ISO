"""Request/response schemas for ``/playbooks/repository``."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import RepositoryType, RepositoryVisibility


class PlaybookRepositoryFolderCreateRequest(BaseModel):
    """Body of ``POST /playbooks/repository``."""

    organization_id: UUID
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    repository_type: RepositoryType = RepositoryType.PROJECT
    visibility: RepositoryVisibility = RepositoryVisibility.PRIVATE


class PlaybookRepositoryFolderResponse(BaseModel):
    """One named grouping of playbooks."""

    id: UUID
    organization_id: UUID
    name: str
    description: str | None
    repository_type: RepositoryType
    visibility: RepositoryVisibility


__all__ = ["PlaybookRepositoryFolderCreateRequest", "PlaybookRepositoryFolderResponse"]
