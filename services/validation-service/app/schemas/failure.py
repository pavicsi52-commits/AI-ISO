"""Response schema for validation failures."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import ValidationSeverity


class ValidationFailureResponse(BaseModel):
    """A durable, trackable record that one validation result failed."""

    id: UUID
    organization_id: UUID
    result_id: UUID
    severity: ValidationSeverity
    reason: str
    is_resolved: bool
    resolved_at: datetime | None
    resolved_by: UUID | None


__all__ = ["ValidationFailureResponse"]
