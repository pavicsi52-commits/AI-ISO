"""Request/response schemas for ``/projects/{id}/settings``."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ProjectSettingsUpdateRequest(BaseModel):
    """Body of ``PUT /projects/{id}/settings``."""

    default_environment: str | None = None
    default_connector_id: UUID | None = None
    default_workflow_runtime: str | None = None
    notification_settings: dict[str, Any] = Field(default_factory=dict)
    retention_policies: dict[str, Any] = Field(default_factory=dict)
    execution_policies: dict[str, Any] = Field(default_factory=dict)
    automation_policies: dict[str, Any] = Field(default_factory=dict)
    validation_policies: dict[str, Any] = Field(default_factory=dict)
    monitoring_policies: dict[str, Any] = Field(default_factory=dict)
    ai_settings: dict[str, Any] = Field(default_factory=dict)
    storage_policies: dict[str, Any] = Field(default_factory=dict)
    security_policies: dict[str, Any] = Field(default_factory=dict)


class ProjectSettingsResponse(BaseModel):
    """One project's settings, in full."""

    id: UUID
    project_id: UUID
    default_environment: str | None
    default_connector_id: UUID | None
    default_workflow_runtime: str | None
    notification_settings: dict[str, Any]
    retention_policies: dict[str, Any]
    execution_policies: dict[str, Any]
    automation_policies: dict[str, Any]
    validation_policies: dict[str, Any]
    monitoring_policies: dict[str, Any]
    ai_settings: dict[str, Any]
    storage_policies: dict[str, Any]
    security_policies: dict[str, Any]
    created_at: datetime
    updated_at: datetime


__all__ = ["ProjectSettingsResponse", "ProjectSettingsUpdateRequest"]
