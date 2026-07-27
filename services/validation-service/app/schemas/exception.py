"""Request/response schemas for validation exceptions (waivers)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ValidationExceptionStatus


class ValidationExceptionRequest(BaseModel):
    """Body of a request to waive a known validation failure."""

    reason: str = Field(min_length=1)
    expires_at: datetime | None = None


class ValidationExceptionDecisionRequest(BaseModel):
    """Body of a request to approve or reject a pending exception."""

    approve: bool
    decision_reason: str | None = None


class ValidationExceptionResponse(BaseModel):
    """A requested, reviewable waiver for one known validation failure."""

    id: UUID
    organization_id: UUID
    failure_id: UUID
    reason: str
    status: ValidationExceptionStatus
    requested_by: UUID
    decided_by: UUID | None
    decided_at: datetime | None
    decision_reason: str | None
    expires_at: datetime | None


__all__ = [
    "ValidationExceptionDecisionRequest",
    "ValidationExceptionRequest",
    "ValidationExceptionResponse",
]
