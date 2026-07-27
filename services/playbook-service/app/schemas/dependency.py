"""Request/response schemas for playbook dependencies."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import DependencyType


class PlaybookDependencyCreateRequest(BaseModel):
    """Body of ``POST /playbooks/{id}/dependencies``."""

    dependency_type: DependencyType
    name: str = Field(min_length=1, max_length=255)
    version_constraint: str | None = Field(default=None, max_length=64)


class PlaybookDependencyResponse(BaseModel):
    """One dependency a playbook requires to run."""

    id: UUID
    playbook_id: UUID
    dependency_type: DependencyType
    name: str
    version_constraint: str | None
    resolved: bool


__all__ = ["PlaybookDependencyCreateRequest", "PlaybookDependencyResponse"]
