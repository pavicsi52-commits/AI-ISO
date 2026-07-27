"""Request/response schemas for ``/validation-results``."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import ValidationCheckType, ValidationResultStatus


class ValidationResultDetailResponse(BaseModel):
    """One raw collected data point backing a validation result."""

    id: UUID
    key: str
    value: Any


class ValidationResultResponse(BaseModel):
    """The outcome of one check against one target within one execution."""

    id: UUID
    organization_id: UUID
    execution_id: UUID
    target_id: UUID
    check_id: UUID
    check_type: ValidationCheckType
    rule_id: UUID | None
    status: ValidationResultStatus
    message: str | None
    evaluated_at: datetime | None
    duration_ms: float | None
    details: list[ValidationResultDetailResponse]


__all__ = ["ValidationResultDetailResponse", "ValidationResultResponse"]
