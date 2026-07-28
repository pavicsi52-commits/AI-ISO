"""Request/response schemas for scheduled synthetic checks."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import SyntheticCheckType


class MonitoringSyntheticTestCreateRequest(BaseModel):
    """Body of a request to register a synthetic check."""

    organization_id: UUID
    target_id: UUID | None = None
    check_type: SyntheticCheckType
    name: str = Field(min_length=1, max_length=255)
    parameters: dict[str, Any] = Field(default_factory=dict)
    interval_seconds: float = Field(default=300.0, gt=0)
    is_active: bool = True


class MonitoringSyntheticTestResponse(BaseModel):
    """A standalone, scheduled synthetic check configuration."""

    id: UUID
    organization_id: UUID
    target_id: UUID | None
    check_type: SyntheticCheckType
    name: str
    parameters: dict[str, Any]
    interval_seconds: float
    is_active: bool


__all__ = ["MonitoringSyntheticTestCreateRequest", "MonitoringSyntheticTestResponse"]
