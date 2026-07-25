"""Request/response schemas for ``/projects``."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ProjectPriority, ProjectStatus, ProjectVisibility


class ProjectCreateRequest(BaseModel):
    """Body of ``POST /projects``."""

    organization_id: UUID
    name: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=1, max_length=64)
    display_name: str | None = None
    description: str | None = None
    visibility: ProjectVisibility = ProjectVisibility.PRIVATE
    default_language: str = "en"
    timezone: str = "UTC"
    category: str | None = None
    priority: ProjectPriority = ProjectPriority.MEDIUM
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectUpdateRequest(BaseModel):
    """Body of ``PUT /projects/{id}``."""

    name: str = Field(min_length=1, max_length=255)
    display_name: str | None = None
    description: str | None = None
    status: ProjectStatus = ProjectStatus.DRAFT
    visibility: ProjectVisibility = ProjectVisibility.PRIVATE
    default_language: str = "en"
    timezone: str = "UTC"
    category: str | None = None
    priority: ProjectPriority = ProjectPriority.MEDIUM
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectPatchRequest(BaseModel):
    """Body of ``PATCH /projects/{id}`` -- every field optional, unlike
    ``PUT``'s full-replace semantics.
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    display_name: str | None = None
    description: str | None = None
    status: ProjectStatus | None = None
    visibility: ProjectVisibility | None = None
    default_language: str | None = None
    timezone: str | None = None
    category: str | None = None
    priority: ProjectPriority | None = None
    metadata: dict[str, Any] | None = None


class ProjectCloneRequest(BaseModel):
    """Body of ``POST /projects/{id}/clone``."""

    name: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=1, max_length=64)


class ProjectArchiveRequest(BaseModel):
    """Body of ``POST /projects/{id}/archive``."""

    reason: str | None = Field(default=None, max_length=1024)


class ProjectResponse(BaseModel):
    """One project, in full."""

    id: UUID
    organization_id: UUID
    name: str
    display_name: str | None
    description: str | None
    code: str
    status: ProjectStatus
    owner_id: UUID
    visibility: ProjectVisibility
    default_language: str
    timezone: str
    category: str | None
    priority: ProjectPriority
    archived_at: datetime | None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


__all__ = [
    "ProjectArchiveRequest",
    "ProjectCloneRequest",
    "ProjectCreateRequest",
    "ProjectPatchRequest",
    "ProjectResponse",
    "ProjectUpdateRequest",
]
