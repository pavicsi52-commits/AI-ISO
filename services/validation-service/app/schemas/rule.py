"""Request/response schemas for the rule engine's own rule catalog."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ValidationResultStatus, ValidationSeverity


class ValidationRuleCreateRequest(BaseModel):
    """Body of a request to create a rule against a check's own collected data."""

    organization_id: UUID
    check_id: UUID
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    condition: str = Field(min_length=1)
    result_status: ValidationResultStatus = ValidationResultStatus.FAILED
    severity: ValidationSeverity = ValidationSeverity.MEDIUM
    weight: float = Field(default=1.0, ge=0)
    remediation_hint: str | None = None
    priority: int = 0


class ValidationRuleResponse(BaseModel):
    """The pass/fail/warn logic evaluated against one check's own collected data."""

    id: UUID
    organization_id: UUID
    check_id: UUID
    name: str
    description: str | None
    condition: str
    result_status: ValidationResultStatus
    severity: ValidationSeverity
    weight: float
    remediation_hint: str | None
    priority: int
    is_active: bool


__all__ = ["ValidationRuleCreateRequest", "ValidationRuleResponse"]
