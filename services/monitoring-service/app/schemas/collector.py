"""Request/response schemas for the distributed collector catalog."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import MonitoringTargetType


class MonitoringCollectorCreateRequest(BaseModel):
    """Body of a request to register a distributed collector."""

    organization_id: UUID
    name: str = Field(min_length=1, max_length=255)
    collector_key: str = Field(min_length=1, max_length=64)
    target_types: list[MonitoringTargetType] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    interval_seconds: float = Field(default=60.0, gt=0)
    is_active: bool = True


class MonitoringCollectorResponse(BaseModel):
    """A reusable, standalone configuration for one distributed collector."""

    id: UUID
    organization_id: UUID
    name: str
    collector_key: str
    target_types: list[str]
    parameters: dict[str, Any]
    interval_seconds: float
    is_active: bool


__all__ = ["MonitoringCollectorCreateRequest", "MonitoringCollectorResponse"]
