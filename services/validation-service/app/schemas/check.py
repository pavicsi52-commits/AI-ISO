"""Request/response schemas for the reusable validation check catalog."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ValidationCheckType


class ValidationCheckCreateRequest(BaseModel):
    """Body of a request to create a reusable validation check."""

    organization_id: UUID
    category_id: UUID | None = None
    check_type: ValidationCheckType
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    collector_key: str = Field(min_length=1, max_length=64)
    parameters: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: float = Field(default=30.0, gt=0)
    retry_count: int = Field(default=0, ge=0)


class ValidationCheckResponse(BaseModel):
    """A standalone, reusable definition of one thing to inspect on a target."""

    id: UUID
    organization_id: UUID
    category_id: UUID | None
    check_type: ValidationCheckType
    name: str
    description: str | None
    collector_key: str
    parameters: dict[str, Any]
    timeout_seconds: float
    retry_count: int


__all__ = ["ValidationCheckCreateRequest", "ValidationCheckResponse"]
