"""Response/request schemas for ``GET /configurations/compliance``."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ComplianceEvalType, ComplianceStatus


class ConfigurationComplianceEvaluateRequest(BaseModel):
    """Body of ``POST /configurations/compliance`` -- record an evaluation result."""

    profile_id: UUID
    eval_type: ComplianceEvalType
    status: ComplianceStatus
    details: dict[str, Any] = Field(default_factory=dict)
    exception_reason: str | None = Field(default=None, max_length=1024)


class ConfigurationComplianceResponse(BaseModel):
    """One compliance-type evaluation recorded against a configuration profile."""

    id: UUID
    profile_id: UUID
    eval_type: ComplianceEvalType
    status: ComplianceStatus
    checked_at: datetime
    details: dict[str, Any]
    exception_reason: str | None


__all__ = ["ConfigurationComplianceEvaluateRequest", "ConfigurationComplianceResponse"]
