"""Request/response schemas for the target dependency graph."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from app.models.enums import DependencyType


class MonitoringDependencyCreateRequest(BaseModel):
    """Body of a request to register a dependency edge between two targets."""

    organization_id: UUID
    parent_target_id: UUID
    child_target_id: UUID
    dependency_type: DependencyType


class MonitoringDependencyResponse(BaseModel):
    """One edge in the target dependency graph."""

    id: UUID
    organization_id: UUID
    parent_target_id: UUID
    child_target_id: UUID
    dependency_type: DependencyType


__all__ = ["MonitoringDependencyCreateRequest", "MonitoringDependencyResponse"]
