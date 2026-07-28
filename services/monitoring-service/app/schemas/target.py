"""Request/response schemas for ``/monitoring/targets``."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import MonitoringTargetType


class MonitoringTargetCreateRequest(BaseModel):
    """Body of ``POST /monitoring/targets``."""

    organization_id: UUID
    project_id: UUID | None = None
    target_type: MonitoringTargetType
    external_id: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    target_metadata: dict[str, Any] = Field(default_factory=dict)


class MonitoringTargetResponse(BaseModel):
    """One registered monitoring target."""

    id: UUID
    organization_id: UUID
    project_id: UUID | None
    target_type: MonitoringTargetType
    external_id: str
    name: str
    target_metadata: dict[str, Any]


__all__ = ["MonitoringTargetCreateRequest", "MonitoringTargetResponse"]
