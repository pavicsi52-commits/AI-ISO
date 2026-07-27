"""Request/response schemas for ``/playbooks``."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ContentType, PlaybookStatus


class PlaybookCreateRequest(BaseModel):
    """Body of ``POST /playbooks``."""

    organization_id: UUID
    project_id: UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    display_name: str | None = Field(default=None, max_length=255)
    description: str | None = None
    content_type: ContentType
    category_id: UUID | None = None
    repository_id: UUID | None = None
    owner_id: UUID | None = None
    author_id: UUID | None = None
    entry_file: str | None = Field(default=None, max_length=512)
    metadata: dict[str, Any] = Field(default_factory=dict)
    initial_content: str = Field(min_length=1)


class PlaybookUpdateRequest(BaseModel):
    """Body of ``PUT /playbooks/{id}``."""

    name: str = Field(min_length=1, max_length=255)
    display_name: str | None = Field(default=None, max_length=255)
    description: str | None = None
    status: PlaybookStatus = PlaybookStatus.DRAFT
    category_id: UUID | None = None
    repository_id: UUID | None = None
    owner_id: UUID | None = None
    author_id: UUID | None = None
    entry_file: str | None = Field(default=None, max_length=512)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PlaybookResponse(BaseModel):
    """One reusable automation content definition."""

    id: UUID
    organization_id: UUID
    project_id: UUID | None
    name: str
    display_name: str | None
    description: str | None
    content_type: ContentType
    status: PlaybookStatus
    current_version: str | None
    category_id: UUID | None
    repository_id: UUID | None
    owner_id: UUID | None
    author_id: UUID | None
    entry_file: str | None
    metadata: dict[str, Any]


class PlaybookImportRequest(BaseModel):
    """Body of ``POST /playbooks/import`` ("Import")."""

    playbook: PlaybookCreateRequest
    tags: list[str] = Field(default_factory=list)
    labels: dict[str, str] = Field(default_factory=dict)


class PlaybookExportResponse(BaseModel):
    """Body of the ``POST /playbooks/export`` response ("Export")."""

    playbook: PlaybookResponse
    content: str
    tags: list[str]
    labels: dict[str, str]


__all__ = [
    "PlaybookCreateRequest",
    "PlaybookExportResponse",
    "PlaybookImportRequest",
    "PlaybookResponse",
    "PlaybookUpdateRequest",
]
