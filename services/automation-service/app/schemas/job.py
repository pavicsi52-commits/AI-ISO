"""Request/response schemas for ``/automation/jobs``."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import AutomationType, ExecutionMode, JobStatus, PlaybookType


class AutomationJobCreateRequest(BaseModel):
    """Body of ``POST /automation/jobs``."""

    organization_id: UUID
    project_id: UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2048)
    automation_type: AutomationType
    playbook_type: PlaybookType
    execution_mode: ExecutionMode = ExecutionMode.MANUAL
    content: str = Field(min_length=1)
    target_selector: dict[str, Any] = Field(default_factory=dict)
    variables: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    timeout_seconds: int | None = Field(default=None, ge=1)
    owner_id: UUID | None = None


class AutomationJobUpdateRequest(BaseModel):
    """Body of ``PUT /automation/jobs/{id}``."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2048)
    status: JobStatus = JobStatus.DRAFT
    automation_type: AutomationType
    playbook_type: PlaybookType
    execution_mode: ExecutionMode
    content: str = Field(min_length=1)
    target_selector: dict[str, Any] = Field(default_factory=dict)
    variables: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    timeout_seconds: int | None = Field(default=None, ge=1)
    owner_id: UUID | None = None


class AutomationJobResponse(BaseModel):
    """One automation job, in full."""

    id: UUID
    organization_id: UUID
    project_id: UUID | None
    name: str
    description: str | None
    automation_type: AutomationType
    playbook_type: PlaybookType
    status: JobStatus
    execution_mode: ExecutionMode
    content: str
    target_selector: dict[str, Any]
    variables: dict[str, Any]
    tags: list[str]
    timeout_seconds: int | None
    owner_id: UUID | None


__all__ = ["AutomationJobCreateRequest", "AutomationJobResponse", "AutomationJobUpdateRequest"]
