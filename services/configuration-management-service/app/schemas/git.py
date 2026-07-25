"""Request/response schemas for ``/configurations/git``."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import GitProvider, GitSyncStatus


class ConfigurationGitRepositoryCreateRequest(BaseModel):
    """Body of ``POST /configurations/git``."""

    organization_id: UUID
    project_id: UUID | None = None
    profile_id: UUID | None = None
    provider: GitProvider
    repository_url: str = Field(min_length=1, max_length=1024)
    branch: str = Field(default="main", min_length=1, max_length=128)
    credential_ref: str | None = Field(default=None, max_length=255)
    webhook_secret_ref: str | None = Field(default=None, max_length=255)


class ConfigurationGitRepositoryUpdateRequest(BaseModel):
    """Body of ``PUT /configurations/git/{id}``."""

    branch: str = Field(default="main", min_length=1, max_length=128)
    credential_ref: str | None = Field(default=None, max_length=255)
    webhook_secret_ref: str | None = Field(default=None, max_length=255)


class ConfigurationGitRepositoryResponse(BaseModel):
    """One Git repository backing a configuration profile's GitOps workflow."""

    id: UUID
    organization_id: UUID
    project_id: UUID | None
    profile_id: UUID | None
    provider: GitProvider
    repository_url: str
    branch: str
    sync_status: GitSyncStatus
    last_synced_at: datetime | None


__all__ = [
    "ConfigurationGitRepositoryCreateRequest",
    "ConfigurationGitRepositoryResponse",
    "ConfigurationGitRepositoryUpdateRequest",
]
